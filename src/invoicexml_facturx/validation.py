"""Validation results: the verdict, findings, and the per-field report."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

LAYER_XSD = "xsd"
"""Layer of XML Schema (XSD) structural findings."""
LAYER_EN16931 = "en16931"
"""Layer of EN 16931 business rule findings."""
LAYER_CIUS = "cius"
"""Layer of national CIUS findings, such as the French BR-FR rules."""


def _extra(data: Mapping[str, Any], known: set[str]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k not in known}


@dataclass
class ValidationFinding:
    """One self-contained finding: the rule that fired, the layer that produced
    it, a plain-language message, the affected field paths, and the verbatim
    validator output. Used by validation results and by rejected create requests.
    """

    message: str
    """The plain-language message."""
    rule: str | None = None
    """The rule identifier, for example ``"BR-CO-10"``. ``None`` for request model errors."""
    layer: str | None = None
    """``"xsd"``, ``"en16931"`` or ``"cius"``. ``None`` for request model errors."""
    line: int | None = None
    """The 1-based invoice line number, or ``None`` for document level findings."""
    fields: list[str] = field(default_factory=list)
    """Field paths into the invoice document, for example ``lines[0].priceDetails.netPrice``."""
    raw: str | None = None
    """The verbatim validator output."""
    additional_properties: dict[str, Any] = field(default_factory=dict)
    """Response fields this version of the library does not model."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ValidationFinding:
        known = {"message", "rule", "layer", "line", "fields", "raw"}
        return cls(message=data.get("message") or "", rule=data.get("rule"), layer=data.get("layer"),
                   line=data.get("line"), fields=list(data.get("fields") or []), raw=data.get("raw"),
                   additional_properties=_extra(data, known))

    def __str__(self) -> str:
        return (f"[{self.rule}] " if self.rule else "") + self.message


@dataclass
class ValidationData:
    """Structured verdict details of a validation run."""

    has_embedded_xml: bool | None = None
    """Whether the uploaded PDF carries an embedded invoice XML. ``None`` for XML uploads."""
    schema_valid: bool | None = None
    """Whether the XML passed the XML Schema (XSD) structural checks."""
    schematron_valid: bool | None = None
    """Whether the XML passed the Schematron business rules."""
    conformance_level: str | None = None
    """The conformance level validated against, for example ``"EN16931"``."""
    profile: str | None = None
    """The slug of the applied profile, for example ``"en16931"``, ``"basic"`` or ``"extended"``."""
    customization_id: str | None = None
    """The specification identifier the document declares."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ValidationData:
        return cls(has_embedded_xml=data.get("hasEmbeddedXml"), schema_valid=data.get("schemaValid"),
                   schematron_valid=data.get("schematronValid"), conformance_level=data.get("conformanceLevel"),
                   profile=data.get("profile"), customization_id=data.get("customizationId"))


@dataclass
class ReportFinding:
    """A finding attached to one row of the field report."""

    rule: str
    message: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.message}"


@dataclass
class ReportRow:
    """One row of the field report: an invoice field, its value, and the findings that reference it."""

    name: str
    """The field name, for example ``"Invoice number"``."""
    section: str
    """``header``, ``seller``, ``buyer``, ``lines``, ``payment``, ``totals`` or ``tax``."""
    path: str
    """The field path into the invoice document."""
    value: str | None
    """The field value for display. Long values are truncated, attachments summarised."""
    is_valid: bool
    """Whether no error references this field."""
    errors: list[ReportFinding] = field(default_factory=list)
    warnings: list[ReportFinding] = field(default_factory=list)
    additional_properties: dict[str, Any] = field(default_factory=dict)
    """Response fields this version of the library does not model."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReportRow:
        known = {"name", "section", "path", "value", "isValid", "errors", "warnings"}
        return cls(name=data.get("name") or "", section=data.get("section") or "", path=data.get("path") or "",
                   value=data.get("value"), is_valid=bool(data.get("isValid")),
                   errors=[ReportFinding(f.get("rule") or "", f.get("message") or "") for f in data.get("errors") or []],
                   warnings=[ReportFinding(f.get("rule") or "", f.get("message") or "") for f in data.get("warnings") or []],
                   additional_properties=_extra(data, known))


@dataclass
class ValidationResult:
    """Result of a validation call.

    Valid and invalid invoices both come back as a result, so check :attr:`valid`.
    Only transport problems (missing file, unreadable XML, authentication) raise.
    """

    valid: bool
    """Whether the invoice is compliant. Warnings never make an invoice invalid."""
    detail: str | None = None
    """A one-sentence summary of the verdict."""
    data: ValidationData = field(default_factory=ValidationData)
    """Schema and Schematron verdicts, conformance level, profile and declared identifier."""
    errors: list[ValidationFinding] = field(default_factory=list)
    """The blocking findings."""
    warnings: list[ValidationFinding] = field(default_factory=list)
    """The advisory findings."""
    report: list[ReportRow] = field(default_factory=list)
    """One row per invoice field with its value and the findings that reference it."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ValidationResult:
        return cls(valid=bool(data.get("valid")), detail=data.get("detail"),
                   data=ValidationData.from_dict(data.get("data") or {}),
                   errors=[ValidationFinding.from_dict(f) for f in data.get("errors") or []],
                   warnings=[ValidationFinding.from_dict(f) for f in data.get("warnings") or []],
                   report=[ReportRow.from_dict(r) for r in data.get("report") or []])
