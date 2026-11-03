"""Turns an ordinary PDF invoice, for example one from an older billing system or a supplier,
into a Factur-X invoice. AI reads the PDF, so a person must check the result before it is used.
The rendered PDF ends with a section of technical properties to make that check easy.
"""

from pathlib import Path

from invoicexml_facturx import (
    ErrorCode,
    FacturXClient,
    FileUpload,
    InvoiceValidationError,
    InvoiceXmlApiError,
    RateLimitError,
)

# Replace these values with your own.
API_KEY = "YOUR_API_KEY"
PDF_PATH = "factures/F-2026-001.pdf"  # an ordinary PDF invoice
OUTPUT_PATH = "F-2026-001-facturx.pdf"


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
        facturx = client.transform_to_facturx(
            pdf,
            # language="fr",                      # optional: left empty, the language the invoice is written in is used
            # preserve_original_pdf=True,         # optional: keep your PDF as the visual layer instead of a new layout
            # include_advanced_properties=False,  # optional: leave out the technical properties section
        )
    except RateLimitError as error:
        # Transform calls are not retried automatically, because a retry repeats the AI read.
        if error.retry_after is not None:
            print(f"Too many requests. Wait {error.retry_after:.0f} seconds before trying again.")
        else:
            print("Too many requests. Wait a moment before trying again.")
        return
    except InvoiceXmlApiError as error:
        if error.error_code == ErrorCode.TOTALS_MISMATCH:
            # The amounts read from the PDF do not add up to its printed total, so no invoice was created.
            print("The lines, allowances, charges and VAT read from the PDF do not add up to its printed total.")
            print("Check the PDF, or create the invoice from your own data with create_facturx instead.")
        elif isinstance(error, InvoiceValidationError):
            # The data read from the PDF would not make a compliant Factur-X invoice.
            print("The invoice read from the PDF is not compliant:")
            for finding in error.errors:
                print(f"  [{finding.rule}] {finding.message} ({', '.join(finding.fields)})")
        else:
            # For example an invalid API key, or a file that is not a PDF invoice.
            print(f"The API refused the request: {error}")
        return

    Path(OUTPUT_PATH).write_bytes(facturx)
    print(f"Saved the Factur-X invoice to {OUTPUT_PATH}. Check it before you send or book it.")


if __name__ == "__main__":
    main()
