from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from invoicexml_facturx import (
    BuyerParty,
    BuyerPostalAddress,
    FacturXClient,
    InvoiceDocument,
    InvoiceLine,
    ItemInformation,
    LineVatInformation,
    PaymentDetails,
    PriceDetails,
    SellerLegalRegistration,
    SellerParty,
    SellerPostalAddress,
)
from invoicexml_facturx.transport import TransportRequest, TransportResponse

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def sample_invoice() -> InvoiceDocument:
    return InvoiceDocument(
        invoice_number="FA-2026-0042",
        issue_date="2026-09-01",
        currency="EUR",
        seller=SellerParty(
            name="Atelier Numerique SARL",
            vat_identifier="FR32123456789",
            legal_registration=SellerLegalRegistration("123456789", "0002"),
            postal_address=SellerPostalAddress(line1="18 Rue de la Republique", city="Lyon", post_code="69002", country="FR"),
        ),
        buyer=BuyerParty(
            name="Librairie Grand Siecle SAS",
            postal_address=BuyerPostalAddress(line1="5 Boulevard Saint-Germain", city="Paris", post_code="75005", country="FR"),
        ),
        payment_details=PaymentDetails(payment_account_identifier="FR7630006000011234567890189"),
        lines=[
            InvoiceLine(quantity=12, item=ItemInformation(name="Maintenance applicative"),
                        price_details=PriceDetails(net_price=Decimal("180.00")), vat_information=LineVatInformation(rate=20)),
            InvoiceLine(quantity=200, item=ItemInformation(name="Guide utilisateur imprime"),
                        price_details=PriceDetails(net_price="4.50"), vat_information=LineVatInformation(rate="5.5")),
        ],
    )


class StubTransport:
    """Records requests and replays queued responses."""

    def __init__(self) -> None:
        self.requests: list[TransportRequest] = []
        self._queue: list[object] = []

    def respond(self, status: int, body: bytes | str = b"", content_type: str | None = None, **headers: str) -> StubTransport:
        hdrs = {k.replace("_", "-"): v for k, v in headers.items()}
        if content_type:
            hdrs["Content-Type"] = content_type
        data = body.encode("utf-8") if isinstance(body, str) else body
        self._queue.append(TransportResponse(status, hdrs, data))
        return self

    def respond_json(self, status: int, payload: str | dict, **headers: str) -> StubTransport:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        kind = "application/problem+json" if status >= 400 else "application/json"
        return self.respond(status, text, kind, **headers)

    def fail(self, error: OSError) -> StubTransport:
        self._queue.append(error)
        return self

    @property
    def last(self) -> TransportRequest:
        return self.requests[-1]

    def send(self, request: TransportRequest) -> TransportResponse:
        self.requests.append(request)
        if not self._queue:
            raise AssertionError(f"No stubbed response left for {request.url}")
        nxt = self._queue.pop(0)
        if isinstance(nxt, OSError):
            raise nxt
        return nxt  # type: ignore[return-value]


@pytest.fixture
def stub() -> StubTransport:
    return StubTransport()


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(stub: StubTransport, sleeps: list[float]) -> FacturXClient:
    c = FacturXClient("test-key", transport=stub)
    c._sleep = sleeps.append
    c._now = lambda: datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
    return c
