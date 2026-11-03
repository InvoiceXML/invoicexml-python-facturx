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
from .emails import EmailMessage, EmailSendResult
from .models import CreateInvoiceRequest, InvoiceDocument, InvoiceOptions, PdfLanguage, RuleSet
from .transport import Transport, TransportRequest, TransportResponse, UrllibTransport
from .validation import ValidationFinding, ValidationReport, ValidationResult

DEFAULT_BASE_URL = "https://api.invoicexml.com"
API_KEY_ENV = "INVOICEXML_API_KEY"

InvoiceInput = InvoiceDocument | Mapping[str, Any]
OptionsInput = InvoiceOptions | Mapping[str, Any] | None
EmailInput = EmailMessage | Mapping[str, Any]
RulesInput = Iterable[RuleSet | str] | None
LanguageInput = PdfLanguage | str | None


class FacturXClient:
    """Client for the Factur-X endpoints of the InvoiceXML API.

    >>> client = FacturXClient()                    # reads INVOICEXML_API_KEY
    >>> pdf = client.create_facturx(invoice)        # Factur-X PDF/A-3 bytes
    >>> result = client.validate_facturx("facture.pdf", rules=[RuleSet.BR_FR])
    >>> sent = client.email_facturx(invoice, EmailMessage(from_=sender, to=buyer))

    Every create call validates the invoice against the full rule set before the
    document is returned. A rejected invoice raises :class:`InvoiceValidationError`
    listing the violated rules. For invoices under the French mandate, add
    ``RuleSet.BR_FR`` to apply the BR-FR rules too.

    HTTP 429 responses are retried automatically after the ``Retry-After`` delay,
    except on transform calls. Other errors raise an :class:`InvoiceXmlApiError` subclass, and network
    failures raise :class:`InvoiceXmlConnectionError`.

    Instances hold no connection state and are safe to share between threads.
    """

    def __init__(self, api_key: str | None = None, *, base_url: str = DEFAULT_BASE_URL, timeout: float = 120.0,
                 max_retries: int = 3, max_retry_wait: float = 60.0, transport: Transport | None = None) -> None:
        """Create a client.

        :param api_key: Your InvoiceXML API key. Defaults to the ``INVOICEXML_API_KEY`` environment variable.
        :param base_url: The API base URL, without the ``/v1`` path.
        :param timeout: Overall timeout of one request, in seconds.
        :param max_retries: How often a request answered with HTTP 429 is retried, on every call except transform.
            0 disables retries.
        :param max_retry_wait: The longest ``Retry-After`` delay, in seconds, the client waits out by itself.
        :param transport: A custom HTTP layer, see :mod:`invoicexml_facturx.transport`.
        """
        key = api_key if api_key is not None else os.environ.get(API_KEY_ENV)
        if not key or not key.strip():
            raise ValueError(f"An API key is required. Pass api_key or set {API_KEY_ENV}. "
                             "Get one at https://www.invoicexml.com/account/signup")
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
        return self._post_json("/v1/create/facturx", invoice, options).body

    def create_cii(self, invoice: InvoiceInput, options: OptionsInput = None) -> str:
        """Create a plain UN/CEFACT CII invoice XML, without a PDF.

        The XML declares the EN 16931 profile, so :meth:`embed_facturx` takes it as is
        to turn your own PDF into a Factur-X invoice. Totals and the VAT breakdown are
        calculated from the lines when omitted.

        :param invoice: The invoice, as a model or a dict in the API's JSON shape.
        :param options: Extra rule sets such as ``RuleSet.BR_FR``, and the ``language`` of
            default texts such as the payment terms. The PDF settings are ignored.
        :returns: The XML document.
        :raises InvoiceValidationError: The invoice violates the rule set.
        """
        return self._post_json("/v1/create/cii", invoice, options).body.decode("utf-8")

    def create_ubl(self, invoice: InvoiceInput, options: OptionsInput = None) -> str:
        """Create a UBL 2.1 invoice XML, without a PDF.

        ``options.profile`` picks the CustomizationID the XML declares and the rule set
        the invoice is validated against, Peppol BIS Billing 3.0 when omitted (see
        :class:`UblProfile`). Totals and the VAT breakdown are calculated from the lines
        when omitted.

        :param invoice: The invoice, as a model or a dict in the API's JSON shape.
        :param options: The UBL ``profile``, extra rule sets such as ``RuleSet.BR_FR``, and
            the ``language`` of default texts such as the payment terms. The PDF settings
            are ignored.
        :returns: The XML document.
        :raises InvoiceValidationError: The invoice violates the rule set.
        """
        return self._post_json("/v1/create/ubl", invoice, options).body.decode("utf-8")

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

    def validate_facturx_report(self, pdf: FileInput, *, rules: RulesInput = None,
                                validation_language: LanguageInput = None) -> ValidationReport:
        """Validate a Factur-X PDF and return the verdict as a printable PDF report.

        Runs the same checks as :meth:`validate_facturx`. A failed verdict is a normal
        result, also for a PDF without embedded XML. Only transport problems (missing
        file, unreadable XML, authentication) raise.

        :param pdf: A path, the PDF bytes, or a :class:`FileUpload`.
        :param rules: Extra rule sets, for example ``[RuleSet.BR_FR]`` for the French mandate.
        :param validation_language: Language of the whole report: en, de or fr. English when omitted.
        :returns: The report PDF and the verdict. Check ``report.valid``.
        :raises InvoiceXmlApiError: An extra rule set needs a higher profile than the invoice declares.
        """
        parts: list[tuple[str, Any]] = [("file", to_upload(pdf))] + _rule_parts(rules)
        parts += _language_part("validationLanguage", validation_language)
        response = self._post_form("/v1/validate/facturx/report", parts)
        return ValidationReport(file=response.body, valid=_verdict(response.header("X-Invoice-Valid")))

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

    # ------------------------------------------------------------------- email

    def email_facturx(self, invoice: InvoiceInput, email: EmailInput, options: OptionsInput = None) -> EmailSendResult:
        """Create a Factur-X hybrid invoice and send it by email.

        Builds the same PDF as :meth:`create_facturx`, then sends a real email
        from your own verified domain. The file does not come back.

        :param invoice: The invoice, as a model or a dict in the API's JSON shape.
        :param email: The email, as an :class:`EmailMessage` or a dict in the API's JSON shape.
        :param options: Extra rule sets such as ``RuleSet.BR_FR``, PDF language, logo,
            brand colour, or your own PDF as the visual layer.
        :returns: The message id. ``accepted`` means handed over for delivery, not yet
            received by the recipient's server.
        :raises InvoiceValidationError: The invoice or the email is invalid.
        :raises InvoiceXmlApiError: With ``ErrorCode.EMAIL_DOMAIN_NOT_VERIFIED`` when the
            sender's domain is not verified.
        """
        if invoice is None:
            raise TypeError("invoice must not be None")
        request = CreateInvoiceRequest(invoice=invoice, options=options)  # type: ignore[arg-type]
        body = _serde.dumps({**request.to_dict(), "email": _email_fields(email)}).encode("utf-8")
        response = self._execute("/v1/create/facturx/email", "application/json", body, accept_json=True)
        return EmailSendResult.from_dict(self._read_json(response, "/v1/create/facturx/email"))

    def email_embedded_facturx(self, pdf: FileInput, xml: FileInput, email: EmailInput, *,
                               rules: RulesInput = None) -> EmailSendResult:
        """Embed a CII invoice XML into an existing PDF and send the Factur-X PDF/A-3 by email.

        Builds the same PDF as :meth:`embed_facturx`, always with the full rule set,
        then sends a real email from your own verified domain. The file does not
        come back.

        :param pdf: The visual PDF.
        :param xml: The CII XML.
        :param email: The email, as an :class:`EmailMessage` or a dict in the API's JSON shape.
        :param rules: Extra rule sets to apply before embedding, such as ``[RuleSet.BR_FR]``.
        :returns: The message id. ``accepted`` means handed over for delivery, not yet
            received by the recipient's server.
        :raises InvoiceValidationError: The XML or the email is invalid.
        :raises InvoiceXmlApiError: With ``ErrorCode.EMAIL_DOMAIN_NOT_VERIFIED`` when the
            sender's domain is not verified.
        """
        parts: list[tuple[str, Any]] = [("pdf", to_upload(pdf)), ("xml", to_upload(xml))]
        parts += _rule_parts(rules) + _email_parts(email)
        response = self._post_form("/v1/embed/facturx/email", parts, accept_json=True)
        return EmailSendResult.from_dict(self._read_json(response, "/v1/embed/facturx/email"))

    # ------------------------------------------------------------------ render

    def render_cii_to_pdf(self, xml: FileInput, *, language: LanguageInput = None, logo_url: str | None = None,
                          include_qr_code: bool | None = None) -> bytes:
        """Render a CII invoice XML, such as the XML of a Factur-X invoice, as a human-readable PDF.

        :param xml: A path, the XML bytes, or a :class:`FileUpload`.
        :param language: Language of the PDF. English when omitted.
        :param logo_url: Public URL of the seller's logo (PNG or JPEG, at most 2 MB).
        :param include_qr_code: Print the EPC payment QR code (GiroCode). Not printed when omitted.
        :returns: The PDF bytes.
        """
        parts: list[tuple[str, Any]] = [("file", to_upload(xml))]
        parts += _language_part("language", language)
        if logo_url is not None:
            parts.append(("logoUrl", logo_url))
        parts += _flag_part("includeQrCode", include_qr_code)
        return self._post_form("/v1/render/cii/to/pdf", parts).body

    # ----------------------------------------------------------------- convert

    def convert_facturx_to_ubl(self, pdf: FileInput, *, validation_language: LanguageInput = None) -> str:
        """Convert the XML embedded in a Factur-X PDF to UBL 2.1.

        :param pdf: A path, the PDF bytes, or a :class:`FileUpload`.
        :param validation_language: Language of the findings of a failed conversion: en, de or fr. English when omitted.
        :returns: The XML document.
        :raises InvoiceValidationError: The invoice violates the rule set.
        :raises InvoiceXmlApiError: With ``ErrorCode.NO_EMBEDDED_XML`` when the PDF carries no invoice XML.
        """
        return self._convert_to_xml("/v1/convert/facturx/to/ubl", pdf, validation_language)

    def convert_facturx_to_cii(self, pdf: FileInput, *, validation_language: LanguageInput = None) -> str:
        """Convert the XML embedded in a Factur-X PDF to a standalone CII XML.

        :param pdf: A path, the PDF bytes, or a :class:`FileUpload`.
        :param validation_language: Language of the findings of a failed conversion: en, de or fr. English when omitted.
        :returns: The XML document.
        :raises InvoiceValidationError: The invoice violates the rule set.
        :raises InvoiceXmlApiError: With ``ErrorCode.NO_EMBEDDED_XML`` when the PDF carries no invoice XML.
        """
        return self._convert_to_xml("/v1/convert/facturx/to/cii", pdf, validation_language)

    def convert_cii_to_facturx(self, xml: FileInput, *, language: LanguageInput = None,
                               validation_language: LanguageInput = None) -> bytes:
        """Convert a CII invoice XML to a Factur-X PDF/A-3 with a rendered PDF.

        :param xml: A path, the XML bytes, or a :class:`FileUpload`.
        :param language: Language of the PDF and of the default texts added to the XML
            when the file has none: en, de or fr. English when omitted.
        :param validation_language: Language of the findings of a failed conversion: en, de or fr. English when omitted.
        :returns: The hybrid PDF bytes.
        :raises InvoiceValidationError: The invoice violates the rule set.
        """
        return self._convert_to_hybrid("/v1/convert/cii/to/facturx", xml, language, validation_language)

    def convert_ubl_to_facturx(self, xml: FileInput, *, language: LanguageInput = None,
                               validation_language: LanguageInput = None) -> bytes:
        """Convert a UBL 2.1 invoice to a Factur-X PDF/A-3 with a rendered PDF.

        :param xml: A path, the XML bytes, or a :class:`FileUpload`.
        :param language: Language of the PDF and of the default texts added to the XML
            when the file has none: en, de or fr. English when omitted.
        :param validation_language: Language of the findings of a failed conversion: en, de or fr. English when omitted.
        :returns: The hybrid PDF bytes.
        :raises InvoiceValidationError: The invoice violates the rule set.
        """
        return self._convert_to_hybrid("/v1/convert/ubl/to/facturx", xml, language, validation_language)

    def convert_xrechnung_to_facturx(self, xml: FileInput, *, language: LanguageInput = None,
                                     validation_language: LanguageInput = None) -> bytes:
        """Convert an XRechnung XML (UBL or CII) to a Factur-X PDF/A-3 with a rendered PDF.

        :param xml: A path, the XML bytes, or a :class:`FileUpload`.
        :param language: Language of the PDF and of the default texts added to the XML
            when the file has none: en, de or fr. English when omitted.
        :param validation_language: Language of the findings of a failed conversion: en, de or fr. English when omitted.
        :returns: The hybrid PDF bytes.
        :raises InvoiceValidationError: The invoice violates the rule set.
        """
        return self._convert_to_hybrid("/v1/convert/xrechnung/to/facturx", xml, language, validation_language)

    # --------------------------------------------------------------- transform

    def transform_to_facturx(self, pdf: FileInput, *, language: LanguageInput = None,
                             preserve_original_pdf: bool | None = None, include_advanced_properties: bool | None = None,
                             validation_language: LanguageInput = None) -> bytes:
        """Read a PDF invoice with AI and return a Factur-X PDF/A-3.

        AI reads the data from the PDF, so a person must check the result before it
        is used. By default the PDF is rendered from the data the AI read and ends
        with an "Electronic invoice details" section, so that data can be checked on
        the pages.

        A 429 on this method is not retried automatically, so wait for ``Retry-After``
        before calling again if you want to retry.

        :param pdf: A path, the PDF bytes, or a :class:`FileUpload`.
        :param language: Language of the rendered PDF and of the default texts in the XML:
            en, de, fr or ``"auto"``. When omitted the API uses ``auto``: the language the
            invoice is written in, English when that is none of the three.
        :param preserve_original_pdf: ``True`` keeps the uploaded PDF as the visual layer and
            only embeds the XML. Its earlier attachments and form fields are not kept.
        :param include_advanced_properties: ``False`` leaves out the "Electronic invoice
            details" section. The section is on when omitted, and ``preserve_original_pdf``
            ignores this setting.
        :param validation_language: Language of the findings of a failed transform: en, de or fr. English when omitted.
        :returns: The hybrid PDF bytes.
        :raises InvoiceValidationError: The invoice the AI read violates the rule set.
        """
        parts: list[tuple[str, Any]] = [("file", to_upload(pdf))]
        parts += _language_part("language", language)
        parts += _flag_part("preserveOriginalPdf", preserve_original_pdf)
        parts += _flag_part("includeAdvancedProperties", include_advanced_properties)
        parts += _language_part("validationLanguage", validation_language)
        return self._post_form("/v1/transform/to/facturx", parts, retry_rate_limit=False).body

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

    def _post_json(self, path: str, invoice: InvoiceInput, options: OptionsInput) -> TransportResponse:
        if invoice is None:
            raise TypeError("invoice must not be None")
        request = CreateInvoiceRequest(invoice=invoice, options=options)  # type: ignore[arg-type]
        body = _serde.dumps(request.to_dict()).encode("utf-8")
        return self._execute(path, "application/json", body, accept_json=False)

    def _post_form(self, path: str, parts: list[tuple[str, Any]], accept_json: bool = False,
                   *, retry_rate_limit: bool = True) -> TransportResponse:
        content_type, body = _multipart(parts)
        return self._execute(path, content_type, body, accept_json=accept_json, retry_rate_limit=retry_rate_limit)

    def _convert_to_xml(self, path: str, pdf: FileInput, validation_language: LanguageInput) -> str:
        parts: list[tuple[str, Any]] = [("file", to_upload(pdf))]
        parts += _language_part("validationLanguage", validation_language)
        return self._post_form(path, parts).body.decode("utf-8")

    def _convert_to_hybrid(self, path: str, xml: FileInput, language: LanguageInput,
                           validation_language: LanguageInput) -> bytes:
        parts: list[tuple[str, Any]] = [("file", to_upload(xml))]
        parts += _language_part("language", language) + _language_part("validationLanguage", validation_language)
        return self._post_form(path, parts).body

    @staticmethod
    def _read_json(response: TransportResponse, path: str) -> Mapping[str, Any]:
        try:
            data = _serde.loads(response.body)
        except ValueError as error:
            raise InvoiceXmlError(f"Cannot read the response of {path}: {error}") from error
        if not isinstance(data, Mapping):
            raise InvoiceXmlError(f"Unexpected response of {path}")
        return data

    def _execute(self, path: str, content_type: str, body: bytes, *, accept_json: bool,
                 retry_rate_limit: bool = True) -> TransportResponse:
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
            if response.status_code == 429 and retry_rate_limit and attempt < self._max_retries:
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


def _language_part(name: str, language: LanguageInput) -> list[tuple[str, Any]]:
    if language is None:
        return []
    value = language.value if isinstance(language, PdfLanguage) else str(language)
    return [(name, value.lower())]


def _flag_part(name: str, value: bool | None) -> list[tuple[str, Any]]:
    return [] if value is None else [(name, "true" if value else "false")]


def _verdict(header: str | None) -> bool | None:
    value = (header or "").strip().lower()
    return True if value == "true" else False if value == "false" else None


def _email_fields(email: EmailInput) -> dict[str, Any]:
    """Return the email as sent, by the same rules on the JSON and the form routes.

    Only ``cc`` and ``bcc`` take a list, because a form route would lose all but the
    first item of any other field. They also take one address, without blank entries.
    """
    if email is None:
        raise TypeError("email must not be None")
    fields: dict[str, Any] = {}
    for key, value in (email.to_dict() if isinstance(email, EmailMessage) else email).items():
        if value is None:
            continue
        if key in ("cc", "bcc"):
            addresses = _copy_addresses(value)
            if addresses:
                fields[key] = addresses
        elif isinstance(value, str):
            fields[key] = value
        else:
            raise TypeError(f"email.{key} takes a single value. Only cc and bcc take a list.")
    return fields


def _copy_addresses(value: Any) -> list[str]:
    items = [value] if isinstance(value, str) else value
    return [item.strip() for item in items if item is not None and item.strip()]


def _email_parts(email: EmailInput) -> list[tuple[str, Any]]:
    parts: list[tuple[str, Any]] = []
    for key, value in _email_fields(email).items():
        for item in [value] if isinstance(value, str) else value:
            parts.append((f"email.{key}", item))
    return parts


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
