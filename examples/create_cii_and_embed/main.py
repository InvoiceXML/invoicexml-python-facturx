"""Builds a CII XML from your invoice data, then embeds it into a PDF you already have.

Use this when your own system prints the invoice PDF and you want it to become a
Factur-X invoice. The CII XML declares the EN 16931 profile, so it embeds as it is.
"""

from decimal import Decimal
from pathlib import Path

from invoicexml_facturx import (
    BuyerParty,
    BuyerPostalAddress,
    FacturXClient,
    FileUpload,
    InvoiceDocument,
    InvoiceLine,
    InvoiceOptions,
    InvoiceValidationError,
    InvoiceXmlApiError,
    ItemInformation,
    LineVatInformation,
    PdfLanguage,
    PriceDetails,
    RuleSet,
    SellerParty,
    SellerPostalAddress,
    VatCategoryCode,
)

# Replace these values with your own.
API_KEY = "YOUR_API_KEY"
PDF_PATH = "factures/F-2026-001.pdf"  # the PDF your system printed
OUTPUT_PATH = "F-2026-001-facturx.pdf"


def main() -> None:
    # Read the PDF first, so a wrong path stops the example before any API call.
    try:
        pdf = FileUpload.from_path(PDF_PATH)
    except FileNotFoundError:
        print(f"Could not find {PDF_PATH}.")
        print("Set PDF_PATH at the top of main.py to a PDF on your machine.")
        return

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
        # 1. Build the CII XML from the invoice data. Language words the default texts, such as the payment terms.
        cii = client.create_cii(invoice, InvoiceOptions(
            language=PdfLanguage.FR,
            # rules=[RuleSet.BR_FR],  # optional: also check the French BR-FR rules (they need more data, see the README)
        ))

        # 2. Embed the XML into your PDF. The result is a Factur-X PDF/A-3.
        facturx = client.embed_facturx(pdf, FileUpload.xml(cii))
    except InvoiceValidationError as error:
        # The invoice data would not produce a compliant invoice. Each finding names the field to fix.
        print("The invoice is not compliant:")
        for finding in error.errors:
            print(f"  [{finding.rule}] {finding.message} ({', '.join(finding.fields)})")
        return
    except InvoiceXmlApiError as error:
        print(f"The API refused the request: {error}")
        return

    Path(OUTPUT_PATH).write_bytes(facturx)
    print(f"Saved the Factur-X invoice to {OUTPUT_PATH}.")


if __name__ == "__main__":
    main()
