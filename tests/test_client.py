from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from conftest import fixture, sample_invoice
from invoicexml_facturx import (
    AuthenticationError,
    ErrorCode,
    FacturXClient,
    FacturXProfile,
    FileUpload,
    InvoiceOptions,
    InvoiceValidationError,
    InvoiceXmlApiError,
    InvoiceXmlConnectionError,
    PayloadTooLargeError,
    PdfLanguage,
    RateLimitError,
    RuleSet,
)
from invoicexml_facturx.validation import LAYER_EN16931

PDF = b"%PDF-1.7 stub"
XML = '<?xml version="1.0"?><rsm:CrossIndustryInvoice/>'


def text(request) -> str:
    return request.body.decode("utf-8")


# ------------------------------------------------------------------- create

def test_create_facturx_posts_json_and_returns_pdf(client, stub):
    stub.respond(200, PDF, "application/pdf")

    assert client.create_facturx(sample_invoice()) == PDF

    r = stub.last
    assert r.url == "https://api.invoicexml.com/v1/create/facturx"
    assert r.header("Authorization") == "Bearer test-key"
    assert r.header("Content-Type") == "application/json"
    assert r.header("User-Agent").startswith("invoicexml-python-facturx/")
    sent = json.loads(r.body)
    invoice = sent["invoice"]
    assert invoice["invoiceNumber"] == "FA-2026-0042"
    assert invoice["issueDate"] == "2026-09-01"
    assert invoice["seller"]["legalRegistration"] == {"identifier": "123456789", "schemeId": "0002"}
    assert '"netPrice":4.50' in text(r)
    assert '"rate":5.5' in text(r)
    assert "options" not in sent


def test_create_facturx_sends_rules_and_rendering_options(client, stub):
    stub.respond(200, PDF, "application/pdf")

    client.create_facturx(sample_invoice(), InvoiceOptions(rules=[RuleSet.BR_FR], language=PdfLanguage.FR,
                                                           brand_color="#0A7C66"))

    options = json.loads(stub.last.body)["options"]
    assert options == {"rules": ["br-fr"], "language": "FR", "brandColor": "#0A7C66"}


def test_create_facturx_sends_profile_identifier(client, stub):
    stub.respond(200, PDF, "application/pdf")
    invoice = sample_invoice()
    invoice.specification_id = FacturXProfile.BASIC

    client.create_facturx(invoice)

    assert json.loads(stub.last.body)["invoice"]["specificationId"] == FacturXProfile.BASIC


def test_create_rejection_carries_findings(client, stub):
    stub.respond_json(400, fixture("create-400.json"))

    with pytest.raises(InvoiceValidationError) as info:
        client.create_facturx(sample_invoice())

    e = info.value
    assert e.error_code == ErrorCode.MODEL_VALIDATION
    assert e.trace_id == "00-abc-def-01"
    finding = e.errors[0]
    assert finding.rule == "BR-CO-26"
    assert finding.layer == LAYER_EN16931
    assert finding.fields == ["seller.vatIdentifier"]
    assert e.invoice_data.type_code == "380"
    assert "BR-CO-26" in str(e)


def test_create_requires_an_invoice(client):
    with pytest.raises(TypeError):
        client.create_facturx(None)  # type: ignore[arg-type]


# ----------------------------------------------------------------- validate

def test_validate_facturx_uploads_path_and_parses_result(client, stub, tmp_path):
    pdf = tmp_path / "facture.pdf"
    pdf.write_bytes(PDF)
    stub.respond_json(200, fixture("validate-facturx-valid.json"))

    result = client.validate_facturx(pdf)

    assert result.valid
    assert result.data.profile == "en16931"
    assert result.data.has_embedded_xml is True
    assert result.report[0].path == "invoiceNumber"
    r = stub.last
    assert r.url.endswith("/v1/validate/facturx")
    assert r.header("Accept") == "application/json"
    body = text(r)
    assert 'Content-Disposition: form-data; name="file"; filename="facture.pdf"' in body
    assert "Content-Type: application/pdf" in body
    assert 'name="rules"' not in body


def test_validate_facturx_sends_rule_sets(client, stub):
    stub.respond_json(200, fixture("validate-facturx-valid.json"))

    client.validate_facturx(PDF, rules=[RuleSet.BR_FR])

    assert text(stub.last).count('name="rules"\r\n\r\nbr-fr\r\n') == 1


def test_invalid_invoice_is_a_result_not_an_exception(client, stub):
    stub.respond_json(200, fixture("validate-facturx-invalid.json"))

    result = client.validate_facturx(PDF)

    assert not result.valid
    assert result.data.schematron_valid is False
    assert result.data.profile == "basic"
    assert result.errors[0].rule == "BR-CO-10"
    assert result.errors[0].fields == ["totals.sumOfLineNetAmounts"]
    assert result.warnings[0].line == 2
    assert not result.report[0].is_valid


# -------------------------------------------------------------------- embed

def test_embed_facturx_sends_pdf_and_xml_parts(client, stub):
    stub.respond(200, PDF, "application/pdf")

    assert client.embed_facturx(PDF, FileUpload.xml(XML)) == PDF

    body = text(stub.last)
    assert stub.last.url.endswith("/v1/embed/facturx")
    assert 'name="pdf"; filename="invoice.pdf"' in body
    assert 'name="xml"; filename="invoice.xml"' in body
    assert "skipValidation" not in body
    assert 'name="rules"' not in body


def test_embed_facturx_sends_options(client, stub):
    stub.respond(200, PDF, "application/pdf")

    client.embed_facturx(PDF, XML.encode(), skip_validation=True, rules=["br-fr"])

    body = text(stub.last)
    assert 'name="skipValidation"\r\n\r\ntrue\r\n' in body
    assert 'name="rules"\r\n\r\nbr-fr\r\n' in body


# ------------------------------------------------------------------ extract

def test_extract_json_returns_the_invoice_model(client, stub):
    stub.respond_json(200, fixture("extract-json.json"))

    invoice = client.extract_json(PDF)

    assert stub.last.url.endswith("/v1/extract/json")
    assert invoice.invoice_number == "FA-2026-0042"
    assert invoice.issue_date == date(2026, 9, 1)
    assert invoice.notes[1].subject_code == "AAB"
    assert invoice.seller.legal_registration.scheme_id == "0002"
    assert invoice.payment_details.payment_means_code == "58"
    assert invoice.totals.grand_total_amount == Decimal("3541.50")
    assert invoice.vat_breakdowns[1].rate == Decimal("5.5")
    assert invoice.supporting_documents[0].attachment == b"hello"


def test_extract_attachments_returns_zip(client, stub):
    stub.respond(200, b"PK\x03\x04", "application/zip")

    assert client.extract_attachments(PDF) == b"PK\x03\x04"
    assert stub.last.url.endswith("/v1/extract/attachments")


# ------------------------------------------------------------------ retries

def test_retries_after_rate_limit_using_retry_after_seconds(client, stub, sleeps):
    stub.respond_json(429, {"title": "Too many requests", "errorCode": 4019}, Retry_After="2")
    stub.respond(200, PDF, "application/pdf")

    assert client.create_facturx(sample_invoice()) == PDF
    assert sleeps == [2.0]
    assert stub.requests[0].body == stub.requests[1].body


def test_retry_after_http_date_is_honoured(client, stub, sleeps):
    stub.respond_json(429, {}, Retry_After="Fri, 09 Oct 2026 12:00:05 GMT")
    stub.respond(200, PDF, "application/pdf")

    client.create_facturx(sample_invoice())

    assert sleeps == [5.0]


def test_rate_limit_surfaces_after_retries_are_used_up(client, stub, sleeps):
    for _ in range(4):
        stub.respond_json(429, {"title": "Too many requests", "errorCode": 4019}, Retry_After="1")

    with pytest.raises(RateLimitError) as info:
        client.create_facturx(sample_invoice())

    assert len(stub.requests) == 4
    assert len(sleeps) == 3
    assert info.value.retry_after == 1.0


def test_retry_after_longer_than_the_cap_fails_fast(client, stub, sleeps):
    stub.respond_json(429, {}, Retry_After="600")

    with pytest.raises(RateLimitError):
        client.create_facturx(sample_invoice())
    assert sleeps == []


def test_missing_retry_after_falls_back_to_backoff(client, stub, sleeps):
    stub.respond_json(429, {}).respond_json(429, {}).respond(200, PDF, "application/pdf")

    client.create_facturx(sample_invoice())

    assert sleeps == [1.0, 2.0]


# ------------------------------------------------------------------- errors

def test_unauthorized_maps_to_authentication_error(client, stub):
    stub.respond_json(401, {"title": "Unauthorized", "detail": "Invalid or inactive API key.", "errorCode": 4010})

    with pytest.raises(AuthenticationError) as info:
        client.validate_facturx(PDF)
    assert info.value.error_code == ErrorCode.UNAUTHORIZED


def test_payload_too_large_maps_to_its_own_error(client, stub):
    stub.respond_json(413, {"title": "Payload too large", "errorCode": 4005})

    with pytest.raises(PayloadTooLargeError):
        client.validate_facturx(PDF)


def test_other_problems_map_to_api_error(client, stub):
    stub.respond_json(400, {"title": "Missing file", "errorCode": 4003})

    with pytest.raises(InvoiceXmlApiError) as info:
        client.validate_facturx(FileUpload.pdf(b""))
    assert not isinstance(info.value, InvoiceValidationError)
    assert info.value.error_code == ErrorCode.MISSING_FILE


def test_non_json_error_body_still_produces_an_error(client, stub):
    stub.respond(500, "<html>oops</html>", "text/html")

    with pytest.raises(InvoiceXmlApiError) as info:
        client.create_facturx(sample_invoice())
    assert info.value.status_code == 500
    assert info.value.response_body == "<html>oops</html>"


def test_io_failure_maps_to_connection_error(client, stub):
    cause = ConnectionResetError("connection reset")
    stub.fail(cause)

    with pytest.raises(InvoiceXmlConnectionError) as info:
        client.create_facturx(sample_invoice())
    assert info.value.__cause__ is cause


# ------------------------------------------------------------ construction

def test_api_key_is_required(monkeypatch):
    monkeypatch.delenv("INVOICEXML_API_KEY", raising=False)
    with pytest.raises(ValueError):
        FacturXClient()


def test_api_key_is_read_from_the_environment(monkeypatch, stub):
    monkeypatch.setenv("INVOICEXML_API_KEY", "env-key")
    stub.respond(200, PDF, "application/pdf")

    FacturXClient(transport=stub).create_facturx(sample_invoice())

    assert stub.last.header("Authorization") == "Bearer env-key"


def test_base_url_trailing_slash_is_ignored(stub):
    stub.respond(200, PDF, "application/pdf")

    FacturXClient("k", base_url="http://localhost:5000/", transport=stub).create_facturx(sample_invoice())

    assert stub.last.url == "http://localhost:5000/v1/create/facturx"


def test_repr_does_not_leak_the_key():
    assert "secret" not in repr(FacturXClient("secret"))
