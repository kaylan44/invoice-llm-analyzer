"""Render ground truth to documents: HTML -> PDF, and optionally a degraded "scan".

Clean documents are born-digital PDFs (selectable text). Degraded documents imitate a
scanned page: the PDF is rasterized, then rotated, blurred, noised and JPEG-compressed, and
wrapped back into a PDF that contains only an image (no text layer), like a real scan.

Degradation is seeded per invoice, so the scans are reproducible. The clean PDFs are not
byte-identical between runs (WeasyPrint stamps a creation date and an ID), which is one
reason the generated documents are committed.
"""

import io
import random
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pypdfium2 as pdfium
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from PIL import Image, ImageFilter
from weasyprint import HTML

from invoice_api.rules import vat_breakdown
from invoice_api.schema import Language
from invoice_evals.generator import GeneratedInvoice

TEMPLATES = Path(__file__).parent / "templates"
LAYOUTS = ("classic", "band")
ACCENTS = ("#1f3a5f", "#5b2a4e", "#2f5d3a")
FONTS = ("DejaVu Sans", "DejaVu Serif", "Ubuntu")

NBSP = " "
MONTHS_EN = (
    "January February March April May June July August September October November December"
).split()

LABELS: dict[Language, dict[str, str]] = {
    "fr": {
        "invoice": "Facture",
        "number": "N°",
        "date": "Date",
        "due": "Échéance",
        "bill_to": "Facturé à",
        "description": "Désignation",
        "qty": "Qté",
        "unit_price": "PU HT",
        "vat": "TVA",
        "amount": "Montant HT",
        "total_excl": "Total HT",
        "total_incl": "Total TTC",
        "on": "sur",
        "vat_number": "TVA intracom.",
        "footer": (
            "Paiement par virement. Pénalités de retard : trois fois le taux d'intérêt légal. "
            f"Indemnité forfaitaire pour frais de recouvrement : 40{NBSP}€."
        ),
    },
    "en": {
        "invoice": "Invoice",
        "number": "Invoice no.",
        "date": "Date",
        "due": "Due date",
        "bill_to": "Bill to",
        "description": "Description",
        "qty": "Qty",
        "unit_price": "Unit price",
        "vat": "VAT",
        "amount": "Amount",
        "total_excl": "Subtotal",
        "total_incl": "Total due",
        "on": "on",
        "vat_number": "VAT Reg. No.",
        "footer": "Payment by bank transfer. Please quote the invoice number as reference.",
    },
}


# --- Formatting (how amounts and dates are printed, per language) ----------------------


def format_number(value: Decimal, language: Language, decimals: int | None = None) -> str:
    """1234.5 -> "1 234,5" (fr) or "1,234.5" (en). ``decimals`` fixes the precision."""
    text = f"{value:,.{decimals}f}" if decimals is not None else f"{value.normalize():,f}"
    if language == "fr":
        # Swap separators through a placeholder: "," -> thin space, "." -> ",".
        text = text.replace(",", "\0").replace(".", ",").replace("\0", NBSP)
    return text


def format_money(value: Decimal, currency: str, language: Language) -> str:
    amount = format_number(value, language, decimals=2)
    symbol = {"EUR": "€", "GBP": "£", "USD": "$"}[currency]
    return f"{amount}{NBSP}{symbol}" if language == "fr" else f"{symbol}{amount}"


def format_date(value: date, language: Language) -> str:
    if language == "fr":
        return value.strftime("%d/%m/%Y")
    return f"{value.day} {MONTHS_EN[value.month - 1]} {value.year}"


def spaced_siret(siret: str) -> str:
    """84215739800012 -> "842 157 398 00012", as printed on French invoices."""
    return f"{siret[:3]} {siret[3:6]} {siret[6:9]} {siret[9:]}"


# --- HTML and PDF ----------------------------------------------------------------------


@dataclass(frozen=True)
class Style:
    layout: str
    accent: str
    font: str


def pick_style(invoice_id: str, seed: int) -> Style:
    rng = random.Random(f"{seed}:{invoice_id}:style")
    return Style(rng.choice(LAYOUTS), rng.choice(ACCENTS), rng.choice(FONTS))


def render_html(invoice: GeneratedInvoice, style: Style) -> str:
    truth = invoice.truth
    lang = truth.language
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=True,  # escape <, &, " in data: a supplier name cannot break the HTML
        undefined=StrictUndefined,  # a typo in the template fails instead of printing ""
    )
    env.filters["fmoney"] = lambda v: format_money(v, truth.currency, lang)
    env.filters["fnum"] = lambda v: format_number(v, lang)
    env.filters["fdate"] = lambda v: format_date(v, lang)
    env.filters["spaced_siret"] = spaced_siret
    return env.get_template("invoice.html.j2").render(
        t=truth,
        r=invoice.render,
        L=LABELS[lang],
        breakdown=vat_breakdown(truth.lines),
        layout=style.layout,
        accent=style.accent,
        font=style.font,
    )


def render_pdf(html: str) -> bytes:
    return HTML(string=html).write_pdf()


# --- Scan degradation ------------------------------------------------------------------


@dataclass(frozen=True)
class Degradation:
    rotation: float  # degrees, sign included
    blur: float  # Gaussian blur radius in pixels
    noise: int  # max amplitude of per-pixel noise (0-255 scale)
    jpeg_quality: int
    dpi: int


PRESETS = {
    "light": dict(rotation=(0.4, 1.2), blur=(0.4, 0.8), noise=(4, 8), jpeg_quality=(55, 70)),
    "heavy": dict(rotation=(1.5, 3.0), blur=(0.9, 1.4), noise=(10, 16), jpeg_quality=(30, 45)),
}


def pick_degradation(level: str, invoice_id: str, seed: int) -> Degradation:
    rng = random.Random(f"{seed}:{invoice_id}:degradation")
    p = PRESETS[level]
    return Degradation(
        rotation=round(rng.uniform(*p["rotation"]) * rng.choice((-1, 1)), 2),
        blur=round(rng.uniform(*p["blur"]), 2),
        noise=rng.randint(*p["noise"]),
        jpeg_quality=rng.randint(*p["jpeg_quality"]),
        dpi=150,
    )


def rasterize(pdf_bytes: bytes, dpi: int) -> Image.Image:
    """First page of a PDF as a grayscale image (PDF units are 1/72 inch)."""
    with pdfium.PdfDocument(pdf_bytes) as pdf:
        return pdf[0].render(scale=dpi / 72).to_pil().convert("L")


def degrade(image: Image.Image, d: Degradation, seed: str) -> Image.Image:
    rng = random.Random(seed)
    out = image.rotate(d.rotation, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    out = out.filter(ImageFilter.GaussianBlur(d.blur))
    # Noise: blend in a random grey image; randbytes is seeded, so the noise is reproducible.
    noise_img = Image.frombytes("L", out.size, rng.randbytes(out.width * out.height))
    out = Image.blend(out, noise_img, d.noise / 255)
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=d.jpeg_quality)  # JPEG artefacts, like a cheap scanner
    return Image.open(io.BytesIO(buf.getvalue()))


def image_to_pdf(image: Image.Image, dpi: int) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PDF", resolution=dpi)
    return buf.getvalue()


def render_document(
    invoice: GeneratedInvoice, seed: int, degradation_level: str | None
) -> tuple[bytes, Style, Degradation | None]:
    """The document sent to the model, plus how it was made (for the manifest)."""
    style = pick_style(invoice.id, seed)
    pdf = render_pdf(render_html(invoice, style))
    if degradation_level is None:
        return pdf, style, None
    d = pick_degradation(degradation_level, invoice.id, seed)
    scan = degrade(rasterize(pdf, d.dpi), d, seed=f"{seed}:{invoice.id}:noise")
    return image_to_pdf(scan, d.dpi), style, d


def describe(style: Style, d: Degradation | None, level: str | None) -> dict[str, object]:
    return {
        "layout": style.layout,
        "font": style.font,
        "degradation": None if d is None else {"level": level, **asdict(d)},
    }
