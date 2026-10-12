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
    UNAUTHORIZED = 4010
    """The API key is missing, unknown or inactive."""
    REMOTE_FETCH_ERROR = 4011
    """A URL given in the options (such as ``pdf_url`` or ``logo_url``) could not be fetched."""
    NO_ATTACHMENTS = 4013
    """The invoice carries no embedded attachments to extract."""
    UNSUPPORTED_PROFILE = 4017
    """The XML declares a specification identifier that is not an official Factur-X profile. See ``FacturXProfile``."""
    TOO_MANY_REQUESTS = 4019
    """Too many concurrent requests for this API key. Retryable after the ``Retry-After`` delay."""


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
    """HTTP 429 after the automatic retries are used up.

    Too many requests for this API key are being processed at the same time.
    Rate-limited requests consume no credits.
    """

    def __init__(self, status_code: int, *, retry_after: float | None = None, **kwargs) -> None:
        self.retry_after = retry_after
        """Seconds the API asked to wait, or ``None`` when no usable header was sent."""
        super().__init__(status_code, **kwargs)
