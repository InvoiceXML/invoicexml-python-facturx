"""AI parse results: the invoice read from a PDF, its confidence scores and its language."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ._serde import to_decimal
from .models import InvoiceDocument


def _score(value: Any) -> Decimal | None:
    return None if value is None else to_decimal(value)


@dataclass
class ParseConfidenceAreas:
    """Confidence per area of the invoice, from 0 (had to guess) to 1 (unambiguous).
    An area is ``None`` when it was not scored."""

    seller_identification: Decimal | None = None
    """How clearly the seller and its identifiers could be read."""
    buyer_identification: Decimal | None = None
    """How clearly the buyer and its identifiers could be read."""
    tax_calculation: Decimal | None = None
    """How clearly the VAT rates, amounts and breakdown could be read."""
    line_items: Decimal | None = None
    """How clearly the lines could be read. Capped when the lines do not add up to the printed totals."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ParseConfidenceAreas:
        return cls(seller_identification=_score(data.get("sellerIdentification")),
                   buyer_identification=_score(data.get("buyerIdentification")),
                   tax_calculation=_score(data.get("taxCalculation")),
                   line_items=_score(data.get("lineItems")))


@dataclass
class ParseConfidence:
    """How sure the read is, from 0 (had to guess) to 1 (unambiguous)."""

    overall: Decimal | None = None
    """The mean of the scored areas, or ``None`` when no area was scored."""
    areas: ParseConfidenceAreas = field(default_factory=ParseConfidenceAreas)
    """The score of each area."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ParseConfidence:
        areas = data.get("areas")
        return cls(overall=_score(data.get("overall")),
                   areas=ParseConfidenceAreas.from_dict(areas if isinstance(areas, Mapping) else {}))


@dataclass
class ParsedInvoice:
    """Result of :meth:`FacturXClient.parse_json`: the invoice the AI read, to be checked
    by a person before it is used."""

    invoice: InvoiceDocument
    """The invoice as read from the PDF."""
    confidence: ParseConfidence | None = None
    """How sure the read is, or ``None`` when the response carried no scores."""
    language: str | None = None
    """Lowercase ISO 639-1 code of the language the invoice is written in, for example ``"fr"``.
    Any language can come back, so it is not always a :class:`PdfLanguage` the create and render methods take.
    ``None`` when it could not be told."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ParsedInvoice:
        confidence = data.get("confidence")
        return cls(invoice=InvoiceDocument.from_dict(data.get("invoice") or {}),
                   confidence=ParseConfidence.from_dict(confidence) if isinstance(confidence, Mapping) else None,
                   language=data.get("language") or None)
