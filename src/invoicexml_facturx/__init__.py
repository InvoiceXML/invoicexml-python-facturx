"""Python client for Factur-X e-invoices via the InvoiceXML API.

Create Factur-X PDF/A-3 hybrids from the EN 16931 model, validate incoming
files (optionally against the French BR-FR rules), embed CII XML into existing
PDFs, and extract invoices back into the model.

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
from .models import *  # noqa: F401,F403
from .models import __all__ as _model_names
from .profiles import FacturXProfile
from .validation import ReportFinding, ReportRow, ValidationData, ValidationFinding, ValidationResult

__all__ = [
    "DEFAULT_BASE_URL",
    "AuthenticationError",
    "ErrorCode",
    "FileInput",
    "FileUpload",
    "InvoiceValidationError",
    "InvoiceXmlApiError",
    "InvoiceXmlConnectionError",
    "InvoiceXmlError",
    "PayloadTooLargeError",
    "RateLimitError",
    "ReportFinding",
    "ReportRow",
    "ValidationData",
    "ValidationFinding",
    "ValidationResult",
    "FacturXClient",
    "FacturXProfile",
    "__version__",
    *_model_names,
]
