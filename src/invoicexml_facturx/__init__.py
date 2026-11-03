"""Python client for Factur-X e-invoices via the InvoiceXML API.

Create Factur-X PDF/A-3 hybrids and plain CII or UBL XML from the EN 16931
model, validate incoming files (optionally against the French BR-FR rules),
embed CII XML into existing PDFs, render invoice XML as PDF, convert between
formats, extract invoices back into the model, and read PDF invoices with AI.

>>> from invoicexml_facturx import FacturXClient
>>> client = FacturXClient()          # reads INVOICEXML_API_KEY
"""

from ._client import DEFAULT_BASE_URL, FacturXClient
from ._errors import (
    AuthenticationError,
    ErrorCode,
    InvoiceValidationError,
    InvoiceXmlApiError,
    InvoiceXmlConnectionError,
    InvoiceXmlError,
    PayloadTooLargeError,
    RateLimitError,
)
from ._files import FileInput, FileUpload
from ._version import __version__
from .emails import EmailMessage, EmailSendResult
from .models import *  # noqa: F401,F403
from .models import __all__ as _model_names
from .parsing import ParseConfidence, ParseConfidenceAreas, ParsedInvoice
from .profiles import FacturXProfile
from .validation import (
    ReportFinding,
    ReportRow,
    ValidationData,
    ValidationFinding,
    ValidationReport,
    ValidationResult,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "AuthenticationError",
    "EmailMessage",
    "EmailSendResult",
    "ErrorCode",
    "FileInput",
    "FileUpload",
    "InvoiceValidationError",
    "InvoiceXmlApiError",
    "InvoiceXmlConnectionError",
    "InvoiceXmlError",
    "ParseConfidence",
    "ParseConfidenceAreas",
    "ParsedInvoice",
    "PayloadTooLargeError",
    "RateLimitError",
    "ReportFinding",
    "ReportRow",
    "ValidationData",
    "ValidationFinding",
    "ValidationReport",
    "ValidationResult",
    "FacturXClient",
    "FacturXProfile",
    "__version__",
    *_model_names,
]
