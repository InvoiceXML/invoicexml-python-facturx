"""Creates a Factur-X invoice that keeps your own PDF layout.

The API downloads your PDF from a public URL, embeds the XML it generates from the invoice
data into it, and returns a Factur-X PDF/A-3. Nothing about your PDF's look changes.
"""

from decimal import Decimal
from pathlib import Path

from invoicexml_facturx import (
    BuyerParty,
    BuyerPostalAddress,
    FacturXClient,
    InvoiceDocument,
    InvoiceLine,
    InvoiceOptions,
    InvoiceValidationError,
    InvoiceXmlApiError,
    ItemInformation,
    LineVatInformation,
    PriceDetails,
    RuleSet,
    SellerParty,
    SellerPostalAddress,
    VatCategoryCode,
)

# Replace these values with your own.
API_KEY = "YOUR_API_KEY"
PDF_URL = "https://example.com/factures/F-2026-001.pdf"  # public http(s) URL of your PDF
OUTPUT_PATH = "F-2026-001-facturx.pdf"


def main() -> None:
    client = FacturXClient(API_KEY)

    invoice = InvoiceDocument(
        invoice_number="F-2026-001",
        currency="EUR",
        seller=SellerParty(
            name="Atelier Dupont SARL",
            vat_identifier="FR32123456789",
            postal_address=SellerPostalAddress(city="Paris", post_code="75011", country="FR"),
        ),
        buyer=BuyerParty(
            name="Client Exemple SA",
            postal_address=BuyerPostalAddress(city="Lyon", post_code="69002", country="FR"),
        ),
        lines=[
            InvoiceLine(
                quantity=10,
                unit_code="HUR",  # hour
                item=ItemInformation(name="Prestation de conseil"),
                price_details=PriceDetails(net_price=Decimal("120")),
                vat_information=LineVatInformation(category_code=VatCategoryCode.STANDARD_RATE, rate=20),
            ),
        ],
    )

    try:
        # pdf_url makes your PDF the visual layer. Without it, the API renders its own invoice layout.
        facturx = client.create_facturx(invoice, InvoiceOptions(
            pdf_url=PDF_URL,
            # rules=[RuleSet.BR_FR],  # optional: also check the French BR-FR rules (they need more data, see the README)
        ))
    except InvoiceValidationError as error:
        # The invoice data would not produce a compliant Factur-X invoice. Each finding names the field to fix.
        print("The invoice is not compliant:")
        for finding in error.errors:
            print(f"  [{finding.rule}] {finding.message} ({', '.join(finding.fields)})")
        return
    except InvoiceXmlApiError as error:
        # For example an invalid API key, or a PDF URL the API could not download.
        print(f"The API refused the request: {error}")
        return

    Path(OUTPUT_PATH).write_bytes(facturx)
    print(f"Saved the Factur-X invoice to {OUTPUT_PATH}.")


if __name__ == "__main__":
    main()
