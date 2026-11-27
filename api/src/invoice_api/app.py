"""FastAPI backend: upload an invoice, process it in the background, read the result.

    uv run uvicorn invoice_api.app:app --reload        # local, reads .env

Every endpoint except /health requires ``Authorization: Bearer <API_TOKEN>``. Without
API_TOKEN configured, the API refuses every request (fails closed): an open upload endpoint
wired to a paid model is the project's main risk (docs/architecture.md, Risques).

Week 2: upload, list, detail, job status. Week 3: document, corrections, validation and
export for the review screen (logic in review.py). Files are stored on local disk
(STORAGE_DIR); Supabase Storage replaces it before real documents are kept.
"""

import os
import secrets
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from psycopg.rows import dict_row

from invoice_api.db import database_url
from invoice_api.embeddings import Embedder, embed
from invoice_api.extraction import MIME_TYPES, make_client
from invoice_api.pipeline import create_invoice, run_job
from invoice_api.review import (
    InvoiceCorrection,
    ReviewError,
    ValidationRequest,
    correct_invoice,
    to_csv,
    validate_invoice,
    validated_rows,
)


@dataclass
class Settings:
    api_token: str | None = field(default_factory=lambda: os.environ.get("API_TOKEN"))
    database_url: str = field(default_factory=database_url)
    storage_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("STORAGE_DIR", "storage"))
    )
    model: str = field(
        default_factory=lambda: os.environ.get("EXTRACTION_MODEL", "gemini-3.5-flash-lite")
    )
    max_upload_mb: int = field(default_factory=lambda: int(os.environ.get("MAX_UPLOAD_MB", "10")))


def create_app(
    settings: Settings | None = None,
    *,
    client: Any | None = None,
    embedder: Embedder | None = None,
) -> FastAPI:
    """Build the app. Tests inject a fake Gemini client and embedder; production uses Gemini."""
    settings = settings or Settings()
    app = FastAPI(title="Invoice extraction API", version="0.2.0")
    state: dict[str, Any] = {"client": client, "embedder": embedder}

    def gemini() -> Any:
        if state["client"] is None:
            state["client"] = make_client()
        return state["client"]

    def embedder_() -> Embedder:
        if state["embedder"] is None:
            state["embedder"] = lambda texts: embed(texts, client=gemini())
        return state["embedder"]

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        if not settings.api_token:
            raise HTTPException(503, "API_TOKEN is not configured: refusing all requests")
        expected = f"Bearer {settings.api_token}"
        # compare_digest takes the same time whatever the input: no timing leak of the token.
        if not authorization or not secrets.compare_digest(authorization, expected):
            raise HTTPException(401, "missing or invalid bearer token")

    def connection() -> Iterator[psycopg.Connection]:
        with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
            yield conn

    Auth = Depends(authorize)
    Conn = Annotated[psycopg.Connection, Depends(connection)]

    def background_job(job_id: UUID, document: bytes, mime_type: str) -> None:
        with psycopg.connect(settings.database_url) as conn:
            run_job(
                conn, job_id, document, mime_type,
                client=gemini(), embedder=embedder_(), model=settings.model,
            )  # fmt: skip

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/invoices", status_code=202, dependencies=[Auth])
    async def upload(file: UploadFile, background: BackgroundTasks, conn: Conn) -> dict[str, Any]:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in MIME_TYPES:
            raise HTTPException(415, f"unsupported file type {suffix!r}: PDF, PNG or JPEG only")
        document = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(document) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"file larger than {settings.max_upload_mb} MB")
        if not document:
            raise HTTPException(400, "empty file")
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        path = settings.storage_dir / f"{uuid.uuid4()}{suffix}"  # never the client's file name
        path.write_bytes(document)
        invoice_id, job_id = create_invoice(conn, str(path))
        background.add_task(background_job, job_id, document, MIME_TYPES[suffix])
        return {"invoice_id": str(invoice_id), "job_id": str(job_id), "status": "queued"}

    @app.get("/invoices", dependencies=[Auth])
    def list_invoices(conn: Conn, status: str | None = None) -> list[dict[str, Any]]:
        query = (
            "select id, status, supplier_name, invoice_number, issue_date, total_incl_vat,"
            " currency, review_reasons, created_at from invoices"
        )
        params: tuple[Any, ...] = ()
        if status:
            query += " where status = %s"
            params = (status,)
        return conn.execute(query + " order by created_at desc", params).fetchall()

    @app.get("/invoices/{invoice_id}", dependencies=[Auth])
    def get_invoice(invoice_id: UUID, conn: Conn) -> dict[str, Any]:
        invoice = conn.execute("select * from invoices where id = %s", (invoice_id,)).fetchone()
        if invoice is None:
            raise HTTPException(404, "invoice not found")
        invoice.pop("file_path")  # internal storage path: the file is served by /document
        invoice["lines"] = conn.execute(
            "select position, description, quantity, unit_price, vat_rate, amount,"
            " category_code, category_score from invoice_lines where invoice_id = %s"
            " order by position",
            (invoice_id,),
        ).fetchall()
        invoice["extraction"] = conn.execute(
            "select model, prompt_version, checks, error, input_tokens, output_tokens,"
            " latency_s, created_at from extractions where invoice_id = %s"
            " order by created_at desc limit 1",
            (invoice_id,),
        ).fetchone()
        invoice["job"] = conn.execute(
            "select id, status, error from jobs where invoice_id = %s"
            " order by created_at desc limit 1",
            (invoice_id,),
        ).fetchone()
        return invoice

    # --- Review (week 3) ----------------------------------------------------------------

    @app.get("/invoices/{invoice_id}/document", dependencies=[Auth])
    def get_document(invoice_id: UUID, conn: Conn) -> FileResponse:
        row = conn.execute("select file_path from invoices where id = %s", (invoice_id,)).fetchone()
        path = Path(row["file_path"]) if row else None
        if path is None or not path.is_file():
            raise HTTPException(404, "document not found")
        # Served through the API (and the Next.js relay), never from a public bucket URL.
        return FileResponse(path, media_type=MIME_TYPES[path.suffix.lower()])

    @app.patch("/invoices/{invoice_id}", dependencies=[Auth])
    def patch_invoice(
        invoice_id: UUID, correction: InvoiceCorrection, conn: Conn
    ) -> dict[str, Any]:
        try:
            found = correct_invoice(conn, invoice_id, correction)
        except ReviewError as exc:
            raise HTTPException(409, str(exc)) from None
        if not found:
            raise HTTPException(404, "invoice not found")
        return get_invoice(invoice_id, conn)

    @app.post("/invoices/{invoice_id}/validate", dependencies=[Auth])
    def post_validate(invoice_id: UUID, request: ValidationRequest, conn: Conn) -> dict[str, Any]:
        try:
            found = validate_invoice(conn, invoice_id, request)
        except ReviewError as exc:
            raise HTTPException(409, str(exc)) from None
        if not found:
            raise HTTPException(404, "invoice not found")
        return get_invoice(invoice_id, conn)

    @app.get("/export", dependencies=[Auth], response_model=None)
    def export(conn: Conn, format: Literal["csv", "json"] = "json") -> Any:
        rows = validated_rows(conn)
        if format == "json":
            return rows
        return Response(
            to_csv(rows),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="invoices.csv"'},
        )

    @app.get("/jobs/{job_id}", dependencies=[Auth])
    def get_job(job_id: UUID, conn: Conn) -> dict[str, Any]:
        job = conn.execute(
            "select id, invoice_id, status, error, created_at, updated_at from jobs where id = %s",
            (job_id,),
        ).fetchone()
        if job is None:
            raise HTTPException(404, "job not found")
        return job

    return app


def _default_app() -> FastAPI:
    load_dotenv()
    return create_app()


app = _default_app()
