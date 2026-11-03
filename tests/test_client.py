from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal

import pytest

from conftest import fixture, sample_invoice
from invoicexml_facturx import (
    AuthenticationError,
    EmailMessage,
    EmailSendResult,
    ErrorCode,
    FacturXClient,
    FacturXProfile,
    FileUpload,
    InvoiceOptions,
    InvoiceValidationError,
    InvoiceXmlApiError,
    InvoiceXmlConnectionError,
    ParseConfidence,
    ParseConfidenceAreas,
    ParsedInvoice,
    PayloadTooLargeError,
    PdfLanguage,
    RateLimitError,
    RuleSet,
    UblProfile,
    ValidationReport,
)
from invoicexml_facturx.validation import LAYER_EN16931

PDF = b"%PDF-1.7 stub"
XML = '<?xml version="1.0"?><rsm:CrossIndustryInvoice/>'
SENT = {"status": "accepted", "messageId": "0102abc"}
CREATE_XML = [("create_cii", "/v1/create/cii"), ("create_ubl", "/v1/create/ubl")]
CONVERT_TO_XML = [("convert_facturx_to_ubl", "/v1/convert/facturx/to/ubl"),
                  ("convert_facturx_to_cii", "/v1/convert/facturx/to/cii")]
CONVERT_TO_HYBRID = [("convert_cii_to_facturx", "/v1/convert/cii/to/facturx"),
                     ("convert_ubl_to_facturx", "/v1/convert/ubl/to/facturx"),
                     ("convert_xrechnung_to_facturx", "/v1/convert/xrechnung/to/facturx")]


def text(request) -> str:
    return request.body.decode("utf-8")


def part_names(request) -> list[str]:
    return re.findall(r'form-data; name="([^"]+)"', text(request))


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
    for method in ("create_cii", "create_ubl"):
        with pytest.raises(TypeError):
            getattr(client, method)(None)


@pytest.mark.parametrize("method, route", CREATE_XML)
def test_create_xml_posts_json_and_returns_the_xml(client, stub, method, route):
    stub.respond(200, XML, "application/xml", Content_Disposition='attachment; filename="invoice-FA-2026-0042.xml"')

    assert getattr(client, method)(sample_invoice()) == XML

    r = stub.last
    assert r.url == "https://api.invoicexml.com" + route
    assert r.header("Content-Type") == "application/json"
    assert r.header("Accept") is None
    sent = json.loads(r.body)
    assert sent["invoice"]["invoiceNumber"] == "FA-2026-0042"
    assert "options" not in sent


@pytest.mark.parametrize("method, route", CREATE_XML)
def test_create_xml_accepts_plain_dicts(client, stub, method, route):
    stub.respond(200, XML, "application/xml")

    getattr(client, method)(sample_invoice().to_dict(), {"language": "DE", "rules": ["br-fr"]})

    sent = json.loads(stub.last.body)
    assert sent["invoice"]["invoiceNumber"] == "FA-2026-0042"
    assert sent["options"] == {"language": "DE", "rules": ["br-fr"]}


@pytest.mark.parametrize("method, route", CREATE_XML)
def test_create_xml_rejection_carries_findings(client, stub, method, route):
    stub.respond_json(400, fixture("create-400.json"))

    with pytest.raises(InvoiceValidationError) as info:
        getattr(client, method)(sample_invoice())

    assert info.value.errors[0].rule == "BR-CO-26"


def test_create_cii_sends_rules_and_language(client, stub):
    stub.respond(200, XML, "application/xml")

    client.create_cii(sample_invoice(), InvoiceOptions(rules=[RuleSet.BR_FR], language=PdfLanguage.FR))

    assert json.loads(stub.last.body)["options"] == {"rules": ["br-fr"], "language": "FR"}


def test_create_ubl_sends_profile_rules_and_language(client, stub):
    stub.respond(200, XML, "application/xml")

    client.create_ubl(sample_invoice(), InvoiceOptions(profile=UblProfile.PEPPOL_BIS_3, rules=[RuleSet.BR_FR],
                                                       language=PdfLanguage.FR))

    assert stub.last.url.endswith("/v1/create/ubl")
    assert json.loads(stub.last.body)["options"] == {"profile": "peppol-bis-3", "rules": ["br-fr"], "language": "FR"}


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


@pytest.mark.parametrize("header, valid", [("true", True), ("false", False), ("False", False), ("maybe", None)])
def test_validation_report_returns_the_pdf_and_the_verdict(client, stub, header, valid):
    stub.respond(200, PDF, "application/pdf", X_Invoice_Valid=header)

    report = client.validate_facturx_report(PDF)

    assert report == ValidationReport(file=PDF, valid=valid)
    assert stub.last.url == "https://api.invoicexml.com/v1/validate/facturx/report"
    assert stub.last.header("Accept") is None
    assert part_names(stub.last) == ["file"]


def test_validation_report_without_the_header_has_no_verdict(client, stub):
    stub.respond(200, PDF, "application/pdf")

    report = client.validate_facturx_report(PDF)

    assert report.file == PDF
    assert report.valid is None


def test_validation_report_sends_one_part_per_rule_and_the_validation_language(client, stub):
    stub.respond(200, PDF, "application/pdf", X_Invoice_Valid="false")

    client.validate_facturx_report(PDF, rules=[RuleSet.BR_FR, "peppol"], validation_language=PdfLanguage.FR)

    body = text(stub.last)
    assert body.count('name="rules"') == 2
    assert 'name="rules"\r\n\r\nbr-fr\r\n' in body
    assert 'name="rules"\r\n\r\npeppol\r\n' in body
    assert 'name="validationLanguage"\r\n\r\nfr\r\n' in body


def test_validation_report_transport_problem_raises(client, stub):
    stub.respond_json(400, {"title": "Missing file", "errorCode": 4003})

    with pytest.raises(InvoiceXmlApiError) as info:
        client.validate_facturx_report(FileUpload.pdf(b""))
    assert info.value.error_code == ErrorCode.MISSING_FILE


def test_validation_report_repr_leaves_out_the_pdf():
    assert "stub" not in repr(ValidationReport(file=PDF, valid=True))


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


# -------------------------------------------------------------------- email

def test_email_facturx_posts_invoice_and_email_and_returns_the_message_id(client, stub):
    stub.respond_json(200, SENT)

    result = client.email_facturx(sample_invoice(), EmailMessage(from_="factures@atelier.fr", to="compta@client.fr"))

    assert result == EmailSendResult(status="accepted", message_id="0102abc")
    r = stub.last
    assert r.method == "POST"
    assert r.url == "https://api.invoicexml.com/v1/create/facturx/email"
    assert r.header("Content-Type") == "application/json"
    assert r.header("Accept") == "application/json"
    sent = json.loads(r.body)
    assert sent["invoice"]["invoiceNumber"] == "FA-2026-0042"
    assert sent["email"] == {"from": "factures@atelier.fr", "to": "compta@client.fr"}, "unset fields are omitted"
    assert "options" not in sent


def test_email_facturx_sends_every_email_field_with_its_wire_key(client, stub):
    stub.respond_json(200, SENT)

    client.email_facturx(sample_invoice(), EmailMessage(
        from_="factures@atelier.fr", to="compta@client.fr", from_name="Atelier", cc=["a@atelier.fr"],
        bcc=["b@atelier.fr"], reply_to="aide@atelier.fr", subject="Facture", message="Bonjour"),
        InvoiceOptions(rules=[RuleSet.BR_FR]))

    sent = json.loads(stub.last.body)
    assert sent["options"] == {"rules": ["br-fr"]}
    assert sent["email"] == {"from": "factures@atelier.fr", "fromName": "Atelier", "to": "compta@client.fr",
                             "cc": ["a@atelier.fr"], "bcc": ["b@atelier.fr"], "replyTo": "aide@atelier.fr",
                             "subject": "Facture", "message": "Bonjour"}


def test_email_accepts_plain_dicts_and_drops_none(client, stub):
    stub.respond_json(200, SENT)

    client.email_facturx({"invoiceNumber": "X-1"}, {"from": "factures@atelier.fr", "to": "c@client.fr", "cc": None})

    assert json.loads(stub.last.body) == {"invoice": {"invoiceNumber": "X-1"},
                                          "email": {"from": "factures@atelier.fr", "to": "c@client.fr"}}


def test_email_embedded_facturx_sends_files_and_form_fields(client, stub):
    stub.respond_json(200, SENT)

    result = client.email_embedded_facturx(PDF, FileUpload.xml(XML), EmailMessage(
        from_="factures@atelier.fr", to="compta@client.fr", from_name="Atelier Numérique",
        cc=["a@atelier.fr", "b@atelier.fr"], bcc=["c@atelier.fr"], reply_to="aide@atelier.fr",
        subject="Facture", message="Bonjour"))

    assert result.status == "accepted"
    assert result.message_id == "0102abc"
    r = stub.last
    assert r.url == "https://api.invoicexml.com/v1/embed/facturx/email"
    assert r.header("Accept") == "application/json"
    assert r.header("Content-Type").startswith("multipart/form-data; boundary=")
    body = text(r)
    assert 'name="pdf"; filename="invoice.pdf"' in body
    assert 'name="xml"; filename="invoice.xml"' in body
    assert 'name="email.from"\r\n\r\nfactures@atelier.fr\r\n' in body
    assert 'name="email.fromName"\r\n\r\nAtelier Numérique\r\n' in body
    assert 'name="email.to"\r\n\r\ncompta@client.fr\r\n' in body
    assert 'name="email.cc"\r\n\r\na@atelier.fr\r\n' in body
    assert 'name="email.cc"\r\n\r\nb@atelier.fr\r\n' in body
    assert body.count('name="email.cc"') == 2, "one form part per address"
    assert 'name="email.bcc"\r\n\r\nc@atelier.fr\r\n' in body
    assert 'name="email.replyTo"\r\n\r\naide@atelier.fr\r\n' in body
    assert 'name="email.subject"\r\n\r\nFacture\r\n' in body
    assert 'name="email.message"\r\n\r\nBonjour\r\n' in body
    assert "skipValidation" not in body
    assert 'name="rules"' not in body


def test_email_embedded_facturx_sends_rule_sets(client, stub):
    stub.respond_json(200, SENT)

    client.email_embedded_facturx(PDF, XML.encode(), EmailMessage(from_="f@atelier.fr", to="c@client.fr"),
                                  rules=[RuleSet.BR_FR])

    assert text(stub.last).count('name="rules"\r\n\r\nbr-fr\r\n') == 1


def test_email_embedded_facturx_omits_unset_fields(client, stub):
    stub.respond_json(200, SENT)

    client.email_embedded_facturx(PDF, XML.encode(), {"from": "f@atelier.fr", "to": "c@client.fr", "cc": None})

    body = text(stub.last)
    assert body.count('name="email.') == 2
    assert 'name="email.from"' in body
    assert 'name="email.to"' in body


def test_a_single_copy_address_is_one_part_not_one_per_letter(client, stub):
    stub.respond_json(200, SENT).respond_json(200, SENT)

    client.email_embedded_facturx(PDF, XML.encode(), {"from": "f@atelier.fr", "to": "c@client.fr", "cc": "a@atelier.fr"})
    client.email_embedded_facturx(PDF, XML.encode(), EmailMessage(from_="f@atelier.fr", to="c@client.fr",
                                                                  bcc="b@atelier.fr"))

    assert text(stub.requests[0]).count('name="email.cc"') == 1
    assert text(stub.requests[1]).count('name="email.bcc"') == 1


def test_email_requires_an_invoice_and_an_email(client):
    message = EmailMessage(from_="f@atelier.fr", to="c@client.fr")
    with pytest.raises(TypeError):
        client.email_facturx(None, message)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        client.email_facturx(sample_invoice(), None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        client.email_embedded_facturx(PDF, XML.encode(), None)  # type: ignore[arg-type]


def test_unverified_sender_domain_surfaces_its_error_code(client, stub):
    stub.respond_json(400, {"title": "Sending domain not verified", "errorCode": 4022,
                            "detail": "The sending domain atelier.fr is not verified yet."})

    with pytest.raises(InvoiceXmlApiError) as info:
        client.email_facturx(sample_invoice(), EmailMessage(from_="f@atelier.fr", to="c@client.fr"))

    assert info.value.status_code == 400
    assert info.value.error_code == ErrorCode.EMAIL_DOMAIN_NOT_VERIFIED
    assert not isinstance(info.value, InvoiceValidationError)


@pytest.mark.parametrize("code, name", [(4020, "EMAIL_NOT_IN_PLAN"), (4021, "EMAIL_SENDING_DISABLED")])
def test_blocked_sending_surfaces_its_error_code(client, stub, code, name):
    stub.respond_json(403, {"title": "Forbidden", "errorCode": code})

    with pytest.raises(InvoiceXmlApiError) as info:
        client.email_embedded_facturx(PDF, XML.encode(), EmailMessage(from_="f@atelier.fr", to="c@client.fr"))

    assert info.value.status_code == 403
    assert info.value.error_code == ErrorCode[name]


def test_email_field_findings_arrive_as_a_validation_error(client, stub):
    stub.respond_json(400, {"title": "Invalid request", "errorCode": 4002,
                            "errors": [{"message": "to is not a valid address.", "fields": ["email.to"]}]})

    with pytest.raises(InvoiceValidationError) as info:
        client.email_facturx(sample_invoice(), EmailMessage(from_="f@atelier.fr", to="nope"))

    assert info.value.error_code == ErrorCode.MODEL_VALIDATION
    assert info.value.errors[0].fields == ["email.to"]


def test_email_is_retried_after_a_rate_limit_only(client, stub, sleeps):
    stub.respond_json(429, {"title": "Too many requests", "errorCode": 4019}, Retry_After="2")
    stub.respond_json(200, SENT)

    assert client.email_facturx(sample_invoice(), EmailMessage(from_="f@atelier.fr", to="c@client.fr")).status == "accepted"
    assert sleeps == [2.0]
    assert len(stub.requests) == 2


def test_email_is_not_retried_after_a_server_error(client, stub):
    stub.respond(502, "bad gateway", "text/plain")

    with pytest.raises(InvoiceXmlApiError):
        client.email_facturx(sample_invoice(), EmailMessage(from_="f@atelier.fr", to="c@client.fr"))
    assert len(stub.requests) == 1


def test_email_is_not_retried_after_a_network_failure(client, stub):
    stub.fail(TimeoutError("timed out"))

    with pytest.raises(InvoiceXmlConnectionError):
        client.email_embedded_facturx(PDF, XML.encode(), EmailMessage(from_="f@atelier.fr", to="c@client.fr"))
    assert len(stub.requests) == 1


@pytest.mark.parametrize("key", ["from", "fromName", "to", "replyTo", "subject", "message"])
def test_email_refuses_a_list_in_a_single_value_field_on_both_route_types(client, stub, key):
    email = {"from": "f@atelier.fr", "to": "c@client.fr", key: ["un@atelier.fr", "deux@atelier.fr"]}

    with pytest.raises(TypeError, match=f"email.{key}"):
        client.email_facturx(sample_invoice(), email)
    with pytest.raises(TypeError, match=f"email.{key}"):
        client.email_embedded_facturx(PDF, XML.encode(), email)
    assert stub.requests == []


def test_email_message_refuses_a_list_in_a_single_value_field(client, stub):
    with pytest.raises(TypeError, match="email.to"):
        client.email_facturx(sample_invoice(), EmailMessage(from_="f@atelier.fr", to=["a@client.fr", "b@client.fr"]))  # type: ignore[arg-type]
    assert stub.requests == []


def test_blank_copy_addresses_are_dropped_on_both_route_types(client, stub):
    stub.respond_json(200, SENT).respond_json(200, SENT)
    email = EmailMessage(from_="f@atelier.fr", to="c@client.fr", cc=[" ", " a@atelier.fr "], bcc=[""])

    client.email_facturx(sample_invoice(), email)
    client.email_embedded_facturx(PDF, XML.encode(), email)

    assert json.loads(stub.requests[0].body)["email"] == {"from": "f@atelier.fr", "to": "c@client.fr",
                                                          "cc": ["a@atelier.fr"]}
    body = text(stub.requests[1])
    assert body.count('name="email.cc"') == 1
    assert 'name="email.cc"\r\n\r\na@atelier.fr\r\n' in body
    assert 'name="email.bcc"' not in body


def test_a_single_copy_address_in_a_dict_is_a_list_on_both_route_types(client, stub):
    stub.respond_json(200, SENT).respond_json(200, SENT)
    email = {"from": "f@atelier.fr", "to": "c@client.fr", "cc": "a@atelier.fr"}

    client.email_facturx(sample_invoice(), email)
    client.email_embedded_facturx(PDF, XML.encode(), email)

    assert json.loads(stub.requests[0].body)["email"]["cc"] == ["a@atelier.fr"]
    assert 'name="email.cc"\r\n\r\na@atelier.fr\r\n' in text(stub.requests[1])


# ------------------------------------------------------------------- render

def test_render_xml_sends_only_what_is_set(client, stub):
    stub.respond(200, PDF, "application/pdf").respond(200, PDF, "application/pdf").respond(200, PDF, "application/pdf")

    assert client.render_xml_to_pdf(XML.encode()) == PDF
    client.render_xml_to_pdf(XML.encode(), language=PdfLanguage.FR, logo_url="https://example.com/logo.png",
                             include_qr_code=True)
    client.render_xml_to_pdf(XML.encode(), include_qr_code=False)

    assert stub.requests[0].url == "https://api.invoicexml.com/v1/render/xml/to/pdf"
    assert 'name="file"; filename="invoice.xml"' in text(stub.requests[0])
    assert part_names(stub.requests[0]) == ["file"]
    assert part_names(stub.requests[1]) == ["file", "language", "logoUrl", "includeQrCode"]
    assert 'name="language"\r\n\r\nfr\r\n' in text(stub.requests[1])
    assert 'name="logoUrl"\r\n\r\nhttps://example.com/logo.png\r\n' in text(stub.requests[1])
    assert 'name="includeQrCode"\r\n\r\ntrue\r\n' in text(stub.requests[1])
    assert 'name="includeQrCode"\r\n\r\nfalse\r\n' in text(stub.requests[2])


# ------------------------------------------------------------------ convert

@pytest.mark.parametrize("method, route", CONVERT_TO_XML)
def test_convert_to_xml_returns_text_and_sends_only_the_file(client, stub, method, route):
    stub.respond(200, XML, "application/xml")

    assert getattr(client, method)(PDF) == XML

    assert stub.last.url == f"https://api.invoicexml.com{route}"
    assert part_names(stub.last) == ["file"]


@pytest.mark.parametrize("method, route", CONVERT_TO_XML)
def test_convert_to_xml_sends_the_validation_language(client, stub, method, route):
    stub.respond(200, XML, "application/xml")

    getattr(client, method)(PDF, validation_language="FR")

    assert part_names(stub.last) == ["file", "validationLanguage"]
    assert 'name="validationLanguage"\r\n\r\nfr\r\n' in text(stub.last)


@pytest.mark.parametrize("method", [name for name, _ in CONVERT_TO_XML])
def test_convert_to_xml_takes_no_language(client, method):
    with pytest.raises(TypeError):
        getattr(client, method)(PDF, language="fr")


@pytest.mark.parametrize("method, route", CONVERT_TO_HYBRID)
def test_convert_to_hybrid_returns_the_pdf_and_sends_only_the_file(client, stub, method, route):
    stub.respond(200, PDF, "application/pdf")

    assert getattr(client, method)(XML.encode()) == PDF

    assert stub.last.url == f"https://api.invoicexml.com{route}"
    assert part_names(stub.last) == ["file"]


@pytest.mark.parametrize("method, route", CONVERT_TO_HYBRID)
def test_convert_to_hybrid_sends_both_languages(client, stub, method, route):
    stub.respond(200, PDF, "application/pdf")

    getattr(client, method)(XML.encode(), language=PdfLanguage.FR, validation_language="de")

    body = text(stub.last)
    assert 'name="language"\r\n\r\nfr\r\n' in body
    assert 'name="validationLanguage"\r\n\r\nde\r\n' in body


def test_convert_rejection_carries_findings(client, stub):
    stub.respond_json(400, fixture("create-400.json"))

    with pytest.raises(InvoiceValidationError) as info:
        client.convert_cii_to_facturx(XML.encode())
    assert info.value.errors[0].rule == "BR-CO-26"


def test_convert_of_a_pdf_without_xml_surfaces_its_error_code(client, stub):
    stub.respond_json(400, {"title": "No embedded XML found", "errorCode": 4006,
                            "errors": [{"message": "The PDF carries no invoice XML."}]})

    with pytest.raises(InvoiceXmlApiError) as info:
        client.convert_facturx_to_ubl(PDF)
    assert info.value.error_code == ErrorCode.NO_EMBEDDED_XML


# ---------------------------------------------------------------- transform

def test_transform_to_facturx_sends_only_the_file(client, stub):
    stub.respond(200, PDF, "application/pdf")

    assert client.transform_to_facturx(PDF) == PDF

    assert stub.last.url == "https://api.invoicexml.com/v1/transform/to/facturx"
    assert part_names(stub.last) == ["file"]


def test_transform_to_facturx_sends_every_option(client, stub):
    stub.respond(200, PDF, "application/pdf")

    client.transform_to_facturx(PDF, language=PdfLanguage.FR, preserve_original_pdf=True,
                                include_advanced_properties=True, validation_language="de")

    body = text(stub.last)
    assert 'name="language"\r\n\r\nfr\r\n' in body
    assert 'name="preserveOriginalPdf"\r\n\r\ntrue\r\n' in body
    assert 'name="includeAdvancedProperties"\r\n\r\ntrue\r\n' in body
    assert 'name="validationLanguage"\r\n\r\nde\r\n' in body


def test_transform_to_facturx_really_sends_false(client, stub):
    stub.respond(200, PDF, "application/pdf")

    client.transform_to_facturx(PDF, preserve_original_pdf=False, include_advanced_properties=False)

    body = text(stub.last)
    assert 'name="preserveOriginalPdf"\r\n\r\nfalse\r\n' in body
    assert 'name="includeAdvancedProperties"\r\n\r\nfalse\r\n' in body


def test_transform_to_facturx_takes_auto(client, stub):
    stub.respond(200, PDF, "application/pdf")

    client.transform_to_facturx(PDF, language="auto")

    assert 'name="language"\r\n\r\nauto\r\n' in text(stub.last)


def test_transform_rejection_carries_findings(client, stub):
    stub.respond_json(400, fixture("create-400.json"))

    with pytest.raises(InvoiceValidationError) as info:
        client.transform_to_facturx(PDF)
    assert info.value.errors[0].rule == "BR-CO-26"


def test_transform_rate_limit_makes_one_request_and_raises(client, stub, sleeps):
    stub.respond_json(429, {"title": "Too many requests", "errorCode": 4019}, Retry_After="2")

    with pytest.raises(RateLimitError) as info:
        client.transform_to_facturx(PDF)

    assert len(stub.requests) == 1
    assert stub.last.url == "https://api.invoicexml.com/v1/transform/to/facturx"
    assert sleeps == []
    assert info.value.retry_after == 2.0
    assert info.value.error_code == ErrorCode.TOO_MANY_REQUESTS


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


# -------------------------------------------------------------------- parse

def test_parse_json_returns_the_invoice_confidence_and_language(client, stub, tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(PDF)
    payload = json.loads(fixture("extract-json.json"))
    payload["confidence"] = {"overall": 0.9, "areas": {"sellerIdentification": 1, "buyerIdentification": 0.95,
                                                       "taxCalculation": None, "lineItems": 0.75}}
    payload["language"] = "fr"
    stub.respond_json(200, payload)

    parsed = client.parse_json(pdf)

    r = stub.last
    assert r.url == "https://api.invoicexml.com/v1/parse/json"
    assert r.header("Accept") == "application/json"
    assert part_names(r) == ["file"]
    assert 'name="file"; filename="scan.pdf"' in text(r)
    assert "Content-Type: application/pdf" in text(r)
    assert parsed.invoice.invoice_number == "FA-2026-0042"
    assert parsed.invoice.totals.grand_total_amount == Decimal("3541.50")
    assert parsed.confidence == ParseConfidence(
        overall=Decimal("0.9"),
        areas=ParseConfidenceAreas(seller_identification=Decimal(1), buyer_identification=Decimal("0.95"),
                                   tax_calculation=None, line_items=Decimal("0.75")))
    assert parsed.language == "fr"


def test_parse_json_without_confidence_or_language(client, stub):
    stub.respond_json(200, {"invoice": {"invoiceNumber": "FA-1"}})

    parsed = client.parse_json(PDF)

    assert parsed == ParsedInvoice(invoice=parsed.invoice)
    assert parsed.invoice.invoice_number == "FA-1"
    assert parsed.confidence is None
    assert parsed.language is None


def test_parse_json_rate_limit_makes_one_request_and_raises(client, stub, sleeps):
    stub.respond_json(429, {"title": "Too many requests", "errorCode": 4019}, Retry_After="2")

    with pytest.raises(RateLimitError) as info:
        client.parse_json(PDF)

    assert len(stub.requests) == 1
    assert sleeps == []
    assert info.value.retry_after == 2.0


def test_parse_json_refusal_maps_to_api_error(client, stub):
    stub.respond_json(400, {"title": "Not an invoice", "errorCode": 4008})

    with pytest.raises(InvoiceXmlApiError) as info:
        client.parse_json(PDF)

    assert info.value.error_code == ErrorCode.NOT_AN_INVOICE


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


def test_render_convert_and_report_retry_after_a_rate_limit(client, stub, sleeps):
    stub.respond_json(429, {}, Retry_After="1").respond(200, PDF, "application/pdf")
    stub.respond_json(429, {}, Retry_After="1").respond(200, XML, "application/xml")
    stub.respond_json(429, {}, Retry_After="1").respond(200, PDF, "application/pdf", X_Invoice_Valid="true")

    client.render_xml_to_pdf(FileUpload.xml(XML))
    client.convert_facturx_to_ubl(PDF)
    client.validate_facturx_report(PDF)

    assert [request.url.removeprefix("https://api.invoicexml.com") for request in stub.requests] == [
        "/v1/render/xml/to/pdf",
        "/v1/render/xml/to/pdf",
        "/v1/convert/facturx/to/ubl",
        "/v1/convert/facturx/to/ubl",
        "/v1/validate/facturx/report",
        "/v1/validate/facturx/report",
    ]
    assert sleeps == [1.0, 1.0, 1.0]


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
