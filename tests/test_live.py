"""Calls the real API and consumes credits (about 13 per run).

Runs only when both INVOICEXML_API_KEY and INVOICEXML_LIVE=1 are set:

    INVOICEXML_LIVE=1 pytest -m live
"""

from __future__ import annotations

import os
import urllib.request
import uuid
from decimal import Decimal

import pytest

from conftest import sample_invoice
from invoicexml_facturx import (
    AdditionalSupportingDocument,
    AuthenticationError,
    BuyerElectronicAddress,
    BuyerLegalRegistration,
    ErrorCode,
    FacturXClient,
    FacturXProfile,
    InvoiceDocument,
    InvoiceNote,
    InvoiceOptions,
    InvoiceValidationError,
    PdfLanguage,
    RuleSet,
    SellerElectronicAddress,
    ValidationResult,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not (os.environ.get("INVOICEXML_API_KEY") and os.environ.get("INVOICEXML_LIVE") == "1"),
                       reason="set INVOICEXML_API_KEY and INVOICEXML_LIVE=1 to call the real API"),
]

BASE_URL = os.environ.get("INVOICEXML_BASE_URL", "https://api.invoicexml.com")


@pytest.fixture(scope="module")
def api() -> FacturXClient:
    return FacturXClient(base_url=BASE_URL)


@pytest.fixture(scope="module")
def facturx_pdf(api) -> bytes:
    return api.create_facturx(sample_invoice(), InvoiceOptions(language=PdfLanguage.FR))


def mandate_invoice() -> InvoiceDocument:
    """The sample invoice with the details the French mandate's BR-FR rules ask for."""
    invoice = sample_invoice()
    invoice.business_process_type = "M1"
    invoice.notes = [
        InvoiceNote("Indemnite forfaitaire pour frais de recouvrement : 40 EUR", "PMT"),
        InvoiceNote("Penalites de retard : trois fois le taux d'interet legal", "PMD"),
        InvoiceNote("Pas d'escompte pour paiement anticipe", "AAB"),
    ]
    invoice.seller.electronic_address = SellerElectronicAddress("123456789", "0225")
    invoice.buyer.legal_registration = BuyerLegalRegistration("987654321", "0002")
    invoice.buyer.electronic_address = BuyerElectronicAddress("987654321", "0225")
    return invoice


def describe(result: ValidationResult) -> str:
    return f"{result.detail} " + "; ".join(str(e) for e in result.errors)


def assert_pdf(data: bytes) -> None:
    assert len(data) > 1000
    assert data[:4] == b"%PDF"


def test_create_facturx(facturx_pdf):
    assert_pdf(facturx_pdf)


def test_validate_facturx(api, facturx_pdf):
    result = api.validate_facturx(facturx_pdf)
    assert result.valid, describe(result)
    assert result.data.has_embedded_xml is True
    assert result.data.profile == "en16931"
    assert result.report


def test_extract_json(api, facturx_pdf):
    invoice = api.extract_json(facturx_pdf)
    assert invoice.invoice_number == "FA-2026-0042"
    assert invoice.seller.postal_address.country == "FR"
    assert len(invoice.lines) == 2
    assert invoice.totals.grand_total_amount == Decimal("3541.50")


def test_french_mandate_rules(api):
    try:
        pdf = api.create_facturx(mandate_invoice(), InvoiceOptions(rules=[RuleSet.BR_FR]))
    except InvoiceValidationError as error:
        pytest.fail(str(error))
    assert_pdf(pdf)
    result = api.validate_facturx(pdf, rules=[RuleSet.BR_FR])
    assert result.valid, describe(result)


def test_basic_profile(api):
    invoice = sample_invoice()
    invoice.specification_id = FacturXProfile.BASIC
    result = api.validate_facturx(api.create_facturx(invoice))
    assert result.valid, describe(result)
    assert result.data.profile == "basic"
    assert result.data.customization_id == FacturXProfile.BASIC


def test_embed_into_own_pdf(api, facturx_pdf):
    hybrid = api.embed_facturx(blank_pdf(), extract_xml(facturx_pdf))
    assert_pdf(hybrid)
    result = api.validate_facturx(hybrid)
    assert result.valid, describe(result)


def test_extract_attachments(api):
    invoice = sample_invoice()
    invoice.supporting_documents = [AdditionalSupportingDocument(
        reference="BL-77", description="Bon de livraison", attachment=b"ligne;quantite\n1;12\n",
        attachment_mime_code="text/csv", attachment_filename="bon-de-livraison.csv")]
    pdf = api.create_facturx(invoice)

    assert api.extract_attachments(pdf)[:2] == b"PK"


def test_rejected_invoice_carries_findings(api):
    invalid = sample_invoice()
    invalid.seller.vat_identifier = None
    invalid.seller.legal_registration = None

    with pytest.raises(InvoiceValidationError) as info:
        api.create_facturx(invalid)
    assert info.value.status_code == 400
    assert info.value.errors, str(info.value)


def test_invalid_key_is_rejected(facturx_pdf):
    bad = FacturXClient("invalid-key", base_url=BASE_URL)
    with pytest.raises(AuthenticationError) as info:
        bad.validate_facturx(facturx_pdf)
    assert info.value.error_code == ErrorCode.UNAUTHORIZED


# ------------------------------------------------------------------ helpers

def extract_xml(pdf: bytes) -> bytes:
    """Read the embedded CII XML of a hybrid PDF through the API's extract/xml endpoint (test-only)."""
    boundary = f"test-{uuid.uuid4().hex}"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"invoice.pdf\"\r\n"
            f"Content-Type: application/pdf\r\n\r\n").encode() + pdf + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(BASE_URL + "/v1/extract/xml", data=body, method="POST", headers={
        "Authorization": "Bearer " + os.environ["INVOICEXML_API_KEY"],
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def blank_pdf() -> bytes:
    """A minimal single-page A4 PDF with a drawn frame and no fonts."""
    content = "0.5 w 50 50 495.28 741.89 re S"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] /Contents 4 0 R /Resources << >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
    ]
    out = "%PDF-1.7\n"
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return out.encode("ascii")
