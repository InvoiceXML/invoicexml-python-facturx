"""The Factur-X client."""

from __future__ import annotations

import os
import platform
import time
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

from . import _serde
from ._errors import (
    AuthenticationError,
    InvoiceValidationError,
    InvoiceXmlApiError,
    InvoiceXmlConnectionError,
    InvoiceXmlError,
    PayloadTooLargeError,
    RateLimitError,
)
from ._files import FileInput, FileUpload, to_upload
from ._version import __version__
from .models import CreateInvoiceRequest, InvoiceDocument, InvoiceOptions, RuleSet
from .transport import Transport, TransportRequest, TransportResponse, UrllibTransport
from .validation import ValidationFinding, ValidationResult

DEFAULT_BASE_URL = "https://api.invoicexml.com"
API_KEY_ENV = "INVOICEXML_API_KEY"

InvoiceInput = InvoiceDocument | Mapping[str, Any]
OptionsInput = InvoiceOptions | Mapping[str, Any] | None
RulesInput = Iterable[RuleSet | str] | None


class FacturXClient:
    """Client for the Factur-X endpoints of the InvoiceXML API.

    >>> client = FacturXClient()                    # reads INVOICEXML_API_KEY
    >>> pdf = client.create_facturx(invoice)        # Factur-X PDF/A-3 bytes
    >>> result = client.validate_facturx("facture.pdf", rules=[RuleSet.BR_FR])

    Every create call validates the invoice against the full rule set before the
    document is returned. A rejected invoice raises :class:`InvoiceValidationError`
    listing the violated rules. For invoices under the French mandate, add
    ``RuleSet.BR_FR`` to apply the BR-FR rules too.

    HTTP 429 responses are retried automatically after the ``Retry-After`` delay.
    Other errors raise an :class:`InvoiceXmlApiError` subclass, and network
    failures raise :class:`InvoiceXmlConnectionError`.

    Instances hold no connection state and are safe to share between threads.
    """

    def __init__(self, api_key: str | None = None, *, base_url: str = DEFAULT_BASE_URL, timeout: float = 120.0,
                 max_retries: int = 3, max_retry_wait: float = 60.0, transport: Transport | None = None) -> None:
        """Create a client.

        :param api_key: Your InvoiceXML API key. Defaults to the ``INVOICEXML_API_KEY`` environment variable.
        :param base_url: The API base URL, without the ``/v1`` path.
        :param timeout: Overall timeout of one request, in seconds.
        :param max_retries: How often a request answered with HTTP 429 is retried. 0 disables retries.
        :param max_retry_wait: The longest ``Retry-After`` delay, in seconds, the client waits out by itself.
        :param transport: A custom HTTP layer, see :mod:`invoicexml_facturx.transport`.
        """
        key = api_key if api_key is not None else os.environ.get(API_KEY_ENV)
        if not key or not key.strip():
            raise ValueError(f"An API key is required. Pass api_key or set {API_KEY_ENV}. "
                             "Get one at https://invoicexml.com/account/signup")
        if not base_url or not base_url.strip():
            raise ValueError("base_url must not be empty")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        self._api_key = key.strip()
        self._base_url = base_url.strip().rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._max_retry_wait = max_retry_wait
        self._transport: Transport = transport or UrllibTransport()
        self._sleep: Callable[[float], None] = time.sleep
        self._now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
        self._user_agent = f"invoicexml-python-facturx/{__version__} (Python {platform.python_version()})"

    def __repr__(self) -> str:
        return f"FacturXClient(base_url={self._base_url!r})"

    # ------------------------------------------------------------------ create

    def create_facturx(self, invoice: InvoiceInput, options: OptionsInput = None) -> bytes:
        """Create a Factur-X hybrid invoice: a PDF/A-3 with the CII XML embedded as ``factur-x.xml``.

        The profile is EN 16931 unless the invoice's ``specification_id`` declares
        another official profile (see :class:`FacturXProfile`). For the MINIMUM
        and BASIC WL profiles the XML carries the header data only, while the PDF
        shows the full lines, so lines remain required input. Totals and the VAT
        breakdown are calculated from the lines when omitted.

        :param invoice: The invoice, as a model or a dict in the API's JSON shape.
        :param options: Extra rule sets such as ``RuleSet.BR_FR``, PDF language, logo,
            brand colour, or your own PDF as the visual layer.
        :returns: The PDF bytes.
        :raises InvoiceValidationError: The invoice violates the rule set.
        """
        if invoice is None:
            raise TypeError("invoice must not be None")
        request = CreateInvoiceRequest(invoice=invoice, options=options)  # type: ignore[arg-type]
        body = _serde.dumps(request.to_dict()).encode("utf-8")
        return self._execute("/v1/create/facturx", "application/json", body, accept_json=False).body

    # ---------------------------------------------------------------- validate

    def validate_facturx(self, pdf: FileInput, *, rules: RulesInput = None) -> ValidationResult:
        """Validate a Factur-X PDF.

        The embedded XML is extracted, its profile detected from the declared
        specification identifier, and the official XSD and Schematron rules for
        that profile applied.

        :param pdf: A path, the PDF bytes, or a :class:`FileUpload`.
        :param rules: Extra rule sets, for example ``[RuleSet.BR_FR]`` for the French mandate.
        :returns: The result. Check ``result.valid``.
        """
        parts: list[tuple[str, Any]] = [("file", to_upload(pdf))] + _rule_parts(rules)
        response = self._post_form("/v1/validate/facturx", parts, accept_json=True)
        return ValidationResult.from_dict(self._read_json(response, "/v1/validate/facturx"))

    # ------------------------------------------------------------------- embed

    def embed_facturx(self, pdf: FileInput, xml: FileInput, *, skip_validation: bool = False,
                      rules: RulesInput = None) -> bytes:
        """Embed a CII invoice XML into an existing PDF and return a Factur-X PDF/A-3.

        :param pdf: The visual PDF.
        :param xml: The CII XML.
        :param skip_validation: Packaging-only mode. By default the XML runs through
            the full rule set before it is embedded, and an invoice with errors is
            rejected. With ``True`` only the structural profile schema check runs.
        :param rules: Extra rule sets to apply before embedding, such as ``[RuleSet.BR_FR]``.
        :returns: The hybrid PDF bytes.
        :raises InvoiceValidationError: The XML violates the rule set.
        """
        parts: list[tuple[str, Any]] = [("pdf", to_upload(pdf)), ("xml", to_upload(xml))]
        if skip_validation:
            parts.append(("skipValidation", "true"))
        parts += _rule_parts(rules)
        return self._post_form("/v1/embed/facturx", parts).body

    # ----------------------------------------------------------------- extract

    def extract_json(self, file: FileInput) -> InvoiceDocument:
        """Read a Factur-X PDF or a CII XML into the invoice model.

        :param file: A path, the file bytes, or a :class:`FileUpload`.
        :returns: The invoice.
        """
        response = self._post_form("/v1/extract/json", [("file", to_upload(file))], accept_json=True)
        return InvoiceDocument.from_dict(self._read_json(response, "/v1/extract/json").get("invoice") or {})

    def extract_attachments(self, file: FileInput) -> bytes:
        """Extract the supporting documents embedded in an invoice as a ZIP archive.

        Payloads are decoded and returned verbatim. External URIs are not fetched.

        :param file: A path, the file bytes, or a :class:`FileUpload`.
        :returns: The ZIP bytes.
        :raises InvoiceXmlApiError: With ``ErrorCode.NO_ATTACHMENTS`` when the invoice carries none.
        """
        return self._post_form("/v1/extract/attachments", [("file", to_upload(file))]).body

    # ---------------------------------------------------------------- plumbing

    def _post_form(self, path: str, parts: list[tuple[str, Any]], accept_json: bool = False) -> TransportResponse:
        content_type, body = _multipart(parts)
        return self._execute(path, content_type, body, accept_json=accept_json)

    @staticmethod
    def _read_json(response: TransportResponse, path: str) -> Mapping[str, Any]:
        try:
            data = _serde.loads(response.body)
        except ValueError as error:
            raise InvoiceXmlError(f"Cannot read the response of {path}: {error}") from error
        if not isinstance(data, Mapping):
            raise InvoiceXmlError(f"Unexpected response of {path}")
        return data

    def _execute(self, path: str, content_type: str, body: bytes, *, accept_json: bool) -> TransportResponse:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": content_type,
            "User-Agent": self._user_agent,
        }
        if accept_json:
            headers["Accept"] = "application/json"
        request = TransportRequest("POST", self._base_url + path, headers, body, self._timeout)

        attempt = 0
        while True:
            try:
                response = self._transport.send(request)
            except OSError as error:
                raise InvoiceXmlConnectionError(f"Request to {path} failed: {error}") from error
            if 200 <= response.status_code < 300:
                return response
            if response.status_code == 429 and attempt < self._max_retries:
                wait = _retry_after(response.header("Retry-After"), self._now())
                if wait is None:
                    wait = float(2 ** min(attempt, 5))
                if wait <= self._max_retry_wait:
                    self._sleep(wait)
                    attempt += 1
                    continue
            raise _to_error(response, self._now())


def _rule_parts(rules: RulesInput) -> list[tuple[str, Any]]:
    if rules is None:
        return []
    if isinstance(rules, (str, RuleSet)):
        rules = [rules]
    return [("rules", rule.value if isinstance(rule, RuleSet) else str(rule)) for rule in rules]


def _multipart(parts: list[tuple[str, Any]]) -> tuple[str, bytes]:
    boundary = f"invoicexml-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in parts:
        chunks.append(f"--{boundary}\r\n".encode("ascii"))
        if isinstance(value, FileUpload):
            file_name = value.file_name.replace("\r", "").replace("\n", "").replace('"', "%22")
            chunks.append(f'Content-Disposition: form-data; name="{name}"; filename="{file_name}"\r\n'.encode("utf-8"))
            chunks.append(f"Content-Type: {value.content_type}\r\n\r\n".encode("ascii"))
            chunks.append(value.content)
        else:
            chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"))
            chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return f"multipart/form-data; boundary={boundary}", b"".join(chunks)


def _retry_after(value: str | None, now: datetime) -> float | None:
    if not value or not value.strip():
        return None
    text = value.strip()
    try:
        seconds = float(int(text))
        return seconds if seconds >= 0 else None
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - now).total_seconds())


def _to_error(response: TransportResponse, now: datetime) -> InvoiceXmlApiError:
    text = response.body.decode("utf-8", errors="replace")
    try:
        data = _serde.loads(response.body) if response.body else None
    except ValueError:
        data = None
    if not isinstance(data, Mapping):
        data = {}

    def as_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    common = {
        "error_code": as_int(data.get("errorCode")),
        "title": data.get("title"),
        "detail": data.get("detail"),
        "trace_id": data.get("traceId"),
        "response_body": text,
    }
    status = response.status_code
    if status == 401:
        return AuthenticationError(status, **common)
    if status == 413:
        return PayloadTooLargeError(status, **common)
    if status == 429:
        return RateLimitError(status, retry_after=_retry_after(response.header("Retry-After"), now), **common)
    if status == 400 and isinstance(data.get("errors"), list):
        invoice_data = data.get("invoiceData")
        return InvoiceValidationError(
            status,
            errors=[ValidationFinding.from_dict(f) for f in data["errors"] if isinstance(f, Mapping)],
            warnings=[ValidationFinding.from_dict(f) for f in data.get("warnings") or [] if isinstance(f, Mapping)],
            invoice_data=InvoiceDocument.from_dict(invoice_data) if isinstance(invoice_data, Mapping) else None,
            **common,
        )
    return InvoiceXmlApiError(status, **common)
