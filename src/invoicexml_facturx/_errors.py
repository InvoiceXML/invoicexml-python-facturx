"""Exceptions raised by the client."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import InvoiceDocument
    from .validation import ValidationFinding


class ErrorCode(enum.IntEnum):
    """Machine-readable error codes carried as ``errorCode`` in problem responses.

    Branch on these instead of parsing titles or messages.
    """

    UNKNOWN = 4000
    """An unexpected error."""
    XML_VALIDATION = 4001
    """The XML is not well-formed or failed schema or business rule validation."""
    MODEL_VALIDATION = 4002
    """The request body is missing required fields or contains invalid values."""
    MISSING_FILE = 4003
    """No file was uploaded."""
    UNSUPPORTED_CONTENT_TYPE = 4004
    """The uploaded file has the wrong type for this endpoint."""
    FILE_TOO_LARGE = 4005
    """The uploaded file exceeds the size limit."""
    NO_EMBEDDED_XML = 4006
    """The uploaded PDF carries no embedded invoice XML."""
    PDF_ERROR = 4007
    """The PDF could not be processed."""
    NOT_AN_INVOICE = 4008
    """The document is not an invoice."""
    MULTIPLE_INVOICES = 4009
    """The document contains more than one invoice."""
    UNAUTHORIZED = 4010
    """The API key is missing, unknown or inactive."""
    REMOTE_FETCH_ERROR = 4011
    """A URL given in the options (such as ``pdf_url`` or ``logo_url``) could not be fetched."""
    NO_ATTACHMENTS = 4013
    """The invoice carries no embedded attachments to extract."""
    INVALID_ATTACHMENT = 4014
    """An embedded attachment could not be decoded."""
    UNEMBEDDABLE_FONT = 4015
    """The supplied PDF uses a font that cannot be embedded, so it cannot become PDF/A-3."""
    REMOTE_FETCH_FORBIDDEN = 4016
    """The host of a PDF or logo URL refused access (HTTP 403)."""
    UNSUPPORTED_PROFILE = 4017
    """The XML declares a specification identifier that is not an official Factur-X profile. See ``FacturXProfile``."""
    TOO_MANY_REQUESTS = 4019
    """Too many concurrent requests for this API key. Retryable after the ``Retry-After`` delay."""
    EMAIL_NOT_IN_PLAN = 4020
    """Your plan does not include email delivery. The pricing page at https://www.invoicexml.com/pricing lists the plans."""
    EMAIL_SENDING_DISABLED = 4021
    """Email sending is disabled or paused for this account."""
    EMAIL_DOMAIN_NOT_VERIFIED = 4022
    """The sender's domain is not verified yet. Check it on the Verified email domains page of your dashboard."""
    PROCESSING_TIMEOUT = 4023
    """The request exceeded the processing time limit (HTTP 503)."""
    TOTALS_MISMATCH = 4024
    """The amounts read from the PDF do not add up to its printed total. Billed; correct invoiceData and create the invoice from it."""


class InvoiceXmlError(Exception):
    """Base class of every exception raised by this library."""


class InvoiceXmlConnectionError(InvoiceXmlError):
    """The API could not be reached or the response could not be read."""


class InvoiceXmlApiError(InvoiceXmlError):
    """The API answered with an error status.

    Carries the RFC 7807 problem details the API returns, including the
    machine-readable :attr:`error_code` (see :class:`ErrorCode`).
    """

    def __init__(self, status_code: int, *, error_code: int | None = None, title: str | None = None,
                 detail: str | None = None, trace_id: str | None = None, response_body: str = "") -> None:
        self.status_code = status_code
        """The HTTP status code."""
        self.error_code = error_code
        """The API error code, or ``None`` when the response carried none."""
        self.title = title
        """The short problem title."""
        self.detail = detail
        """The human-readable problem detail."""
        self.trace_id = trace_id
        """The trace identifier. Quote it when contacting support."""
        self.response_body = response_body
        """The raw response body."""
        super().__init__(self._message())

    def _message(self) -> str:
        text = f"HTTP {self.status_code}"
        if self.error_code is not None:
            text += f" (error {self.error_code})"
        if self.title:
            text += f": {self.title}"
        if self.detail:
            text += f". {self.detail}"
        return text


class InvoiceValidationError(InvoiceXmlApiError):
    """HTTP 400 with a list of findings.

    On the create endpoints the invoice failed the rule set before any document
    was produced, so a non-compliant invoice never leaves your system.
    :attr:`errors` lists the violated rules with the affected fields.
    """

    def __init__(self, status_code: int, *, errors: list[ValidationFinding], warnings: list[ValidationFinding],
                 invoice_data: InvoiceDocument | None = None, **kwargs) -> None:
        self.errors = errors
        """The blocking findings."""
        self.warnings = warnings
        """The advisory findings."""
        self.invoice_data = invoice_data
        """The invoice as the API parsed it, including calculated defaults."""
        super().__init__(status_code, **kwargs)

    def _message(self) -> str:
        lines = [super()._message()]
        lines += [f"  {finding}" for finding in self.errors]
        return "\n".join(lines)


class AuthenticationError(InvoiceXmlApiError):
    """HTTP 401: the API key is missing, unknown or inactive."""


class PayloadTooLargeError(InvoiceXmlApiError):
    """HTTP 413: an uploaded file exceeds the size limit (20 MB per file)."""


class RateLimitError(InvoiceXmlApiError):
    """HTTP 429 after the automatic retries are used up, or the first 429 of a transform or parse call.

    Too many requests for this API key are being processed at the same time.
    A 429 is not billed.
    """

    def __init__(self, status_code: int, *, retry_after: float | None = None, **kwargs) -> None:
        self.retry_after = retry_after
        """Seconds the API asked to wait, or ``None`` when no usable header was sent."""
        super().__init__(status_code, **kwargs)
