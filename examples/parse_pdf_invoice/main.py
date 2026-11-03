"""Reads an ordinary PDF invoice, typed, scanned or photographed, into the InvoiceDocument model.

AI reads the PDF, so a person must check the data before it is used. The result says how sure
the read was per area, which tells the person where to look first.
To read a Factur-X PDF or a CII XML, use the extract_json_and_attachments example instead:
it reads the embedded XML exactly, without AI.
"""

from decimal import Decimal

from invoicexml_facturx import FacturXClient, FileUpload, InvoiceXmlApiError, RateLimitError

# Replace these values with your own.
API_KEY = "YOUR_API_KEY"
PDF_PATH = "factures/facture-fournisseur.pdf"  # an ordinary PDF invoice
CHECK_BELOW = Decimal("0.8")  # areas scored below this are flagged for a closer check


def flag(area: str, score: Decimal | None) -> None:
    if score is None:
        print(f"  {area}: - (no score)")
    else:
        print(f"  {area}: {score} ({'check this closely' if score < CHECK_BELOW else 'ok'})")


def main() -> None:
    # Read the PDF first, so a wrong path stops the example before any API call.
    try:
        pdf = FileUpload.from_path(PDF_PATH)
    except FileNotFoundError:
        print(f"Could not find {PDF_PATH}.")
        print("Set PDF_PATH at the top of main.py to a PDF invoice on your machine.")
        return

    client = FacturXClient(API_KEY)

    try:
        parsed = client.parse_json(pdf)
    except RateLimitError as error:
        # Parse calls are not retried automatically, because a retry repeats the AI read.
        if error.retry_after is not None:
            print(f"Too many requests. Wait {error.retry_after:.0f} seconds before trying again.")
        else:
            print("Too many requests. Wait a moment before trying again.")
        return
    except InvoiceXmlApiError as error:
        # For example an invalid API key, or a file that is not a PDF invoice.
        print(f"The API refused the request: {error}")
        return

    invoice = parsed.invoice
    seller = invoice.seller.name if invoice.seller else None
    buyer = invoice.buyer.name if invoice.buyer else None
    totals = invoice.totals
    print(f"Invoice {invoice.invoice_number} from {seller} to {buyer}")
    print(f"Total {totals.grand_total_amount if totals else None} {invoice.currency}, "
          f"due {totals.due_payable_amount if totals else None}")
    for line in invoice.lines or []:
        item = line.item.name if line.item else None
        price = line.price_details.net_price if line.price_details else None
        print(f"  {line.quantity} x {item} at {price}")

    # The language the invoice is written in, as an ISO 639-1 code such as "fr". None when unknown.
    print(f"Language: {parsed.language or 'unknown'}")

    # Scores run from 0.0 (had to guess) to 1.0 (unambiguous). They can be missing.
    if parsed.confidence is not None:
        overall = parsed.confidence.overall
        print(f"Confidence overall: {'-' if overall is None else overall}")
        areas = parsed.confidence.areas
        flag("seller", areas.seller_identification)
        flag("buyer", areas.buyer_identification)
        flag("VAT", areas.tax_calculation)
        flag("lines", areas.line_items)

    # The checked invoice can be passed straight to a create method, for example
    # client.create_facturx(invoice) to turn it into a Factur-X invoice.


if __name__ == "__main__":
    main()
