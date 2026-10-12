from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from conftest import sample_invoice
from invoicexml_facturx import (
    AdditionalSupportingDocument,
    InvoiceDocument,
    InvoiceNote,
    InvoiceOptions,
    PriceDetails,
    RuleSet,
    SellerIdentifier,
    VatCategoryCode,
)
from invoicexml_facturx._serde import dumps, loads


def test_invoice_round_trips_through_json():
    original = sample_invoice()
    original.notes = ["Plain note", InvoiceNote("Indemnite forfaitaire pour frais de recouvrement : 40 EUR", "PMT")]

    copy = InvoiceDocument.from_dict(loads(dumps(original.to_dict())))

    assert copy.invoice_number == original.invoice_number
    assert copy.issue_date == date(2026, 9, 1)
    assert copy.notes[1].subject_code == "PMT"
    assert copy.lines[1].vat_information.rate == Decimal("5.5")
    assert copy.seller == original.seller


def test_notes_are_sent_as_objects():
    assert InvoiceDocument(notes=[InvoiceNote("Penalites", "PMD")]).to_dict() == {
        "notes": [{"note": "Penalites", "subjectCode": "PMD"}]}


def test_numbers_are_exact():
    payload = dumps(PriceDetails(net_price=0.1, gross_price="19.990").to_dict())
    assert payload == '{"netPrice":0.1,"grossPrice":19.990}'
    assert json.loads(payload)["netPrice"] == 0.1


def test_booleans_are_not_numbers():
    with pytest.raises(TypeError):
        PriceDetails(net_price=True).to_dict()


def test_rules_round_trip():
    assert InvoiceOptions(rules=[RuleSet.BR_FR]).to_dict() == {"rules": ["br-fr"]}
    assert InvoiceOptions(rules=["br-fr"]).to_dict() == {"rules": ["br-fr"]}
    assert InvoiceOptions.from_dict({"rules": ["br-fr"]}).rules == [RuleSet.BR_FR]
    assert InvoiceOptions.from_dict({"rules": ["future-set"]}).rules == ["future-set"]


def test_records_take_positional_arguments():
    assert SellerIdentifier("12345678900012", "0009").to_dict() == {"identifier": "12345678900012", "schemeId": "0009"}
    assert SellerIdentifier("12345678900012").scheme_id is None
    assert VatCategoryCode.STANDARD_RATE == "S"


def test_bytes_are_base64():
    doc = AdditionalSupportingDocument(attachment=b"hello")
    assert doc.to_dict() == {"attachment": "aGVsbG8="}
    assert AdditionalSupportingDocument.from_dict({"attachment": "aGVsbG8="}).attachment == b"hello"
