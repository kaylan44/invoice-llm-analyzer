"""Invoice schema.

Two families of models with two roles:

- ``InvoiceTruth`` / ``InvoiceLine``: ground truth written by the synthetic generator.
  Strict: an invalid value is a bug in the generator and must fail loudly.
- ``InvoiceExtraction`` / ``LineExtraction``: what the model returns. Permissive: any field
  may be missing, and odd values (an unknown currency) are kept so the consistency checks
  can flag them instead of the parser hiding them.

Money is ``Decimal``, never ``float``: amounts must add up exactly.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["fr", "en"]
Currency = Literal["EUR", "GBP", "USD"]

# Reusable constrained types. Annotated[T, ...] = "type T plus metadata"; pydantic reads it.
Amount = Annotated[Decimal, Field(ge=0)]
Quantity = Annotated[Decimal, Field(gt=0)]
VatRate = Annotated[Decimal, Field(ge=0, le=100, description="VAT rate in percent, e.g. 20 or 5.5")]


# --- Ground truth ----------------------------------------------------------------------


class InvoiceLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str = Field(min_length=1)
    quantity: Quantity
    unit_price: Amount
    vat_rate: VatRate
    amount: Amount


class InvoiceTruth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    supplier_name: str = Field(min_length=1)
    supplier_vat_number: str | None
    supplier_siret: str | None
    invoice_number: str = Field(min_length=1)
    issue_date: date
    due_date: date | None
    currency: Currency
    total_excl_vat: Amount
    total_vat: Amount
    total_incl_vat: Amount
    language: Language
    lines: list[InvoiceLine] = Field(min_length=1)


# --- Model output ----------------------------------------------------------------------
# Descriptions end up in the JSON schema sent to Gemini: they are part of the prompt.


class LineExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(description="Line label as printed on the invoice")
    quantity: Decimal | None = None
    unit_price: Decimal | None = Field(default=None, description="Unit price excluding VAT")
    vat_rate: Decimal | None = Field(default=None, description="VAT rate in percent, e.g. 20")
    amount: Decimal | None = Field(default=None, description="Line total excluding VAT")


class InvoiceExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_name: str | None = Field(default=None, description="Supplier name as printed")
    supplier_vat_number: str | None = Field(
        default=None, description="Intra-EU or UK VAT number, without spaces"
    )
    supplier_siret: str | None = Field(
        default=None, description="French SIRET (14 digits), without spaces, if printed"
    )
    invoice_number: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    currency: str | None = Field(default=None, description="ISO 4217 code, e.g. EUR")
    total_excl_vat: Decimal | None = None
    total_vat: Decimal | None = None
    total_incl_vat: Decimal | None = None
    language: Language | None = Field(default=None, description="Language of the invoice")
    lines: list[LineExtraction] = Field(default_factory=list)
