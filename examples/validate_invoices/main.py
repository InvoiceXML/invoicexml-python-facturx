"""Validates an incoming Factur-X invoice against the rules of the profile it declares, and
optionally the French BR-FR rules.

A failed validation is a normal result, not an exception: you get the verdict and every
finding with the rule, the message and the field it concerns. The example also saves the
printable validation report PDF, for example to send back to a supplier.
"""

from pathlib import Path

from invoicexml_facturx import FacturXClient, FileUpload, InvoiceXmlApiError, PdfLanguage, RuleSet

# Replace these values with your own.
API_KEY = "YOUR_API_KEY"
FACTURX_PDF_PATH = "factures/facture-fournisseur.pdf"
REPORT_PATH = "facture-fournisseur-rapport.pdf"

# Optional: also check the French BR-FR rules, the set the French platforms apply to domestic invoices.
RULES: list[RuleSet] = []  # for example [RuleSet.BR_FR]


def main() -> None:
    # Read the PDF first, so a wrong path stops the example before any API call.
    try:
        pdf = FileUpload.from_path(FACTURX_PDF_PATH)
    except FileNotFoundError:
        print(f"Could not find {FACTURX_PDF_PATH}.")
        print("Set FACTURX_PDF_PATH at the top of main.py to a Factur-X PDF on your machine.")
        return

    client = FacturXClient(API_KEY)

    try:
        # 1. The verdict and the findings as data.
        result = client.validate_facturx(pdf, rules=RULES)

        # 2. The same check as a printable PDF report, worded in French.
        report = client.validate_facturx_report(pdf, rules=RULES, validation_language=PdfLanguage.FR)
    except InvoiceXmlApiError as error:
        # For example an invalid API key, or a file that is not a PDF.
        print(f"The API refused the request: {error}")
        return

    print(f"{'Valid' if result.valid else 'Not valid'}. {result.detail or ''}")

    for finding in result.errors:
        print(f"  error   [{finding.rule}] {finding.message} ({', '.join(finding.fields)})")

    # Warnings never make an invoice invalid, but are worth reviewing.
    for finding in result.warnings:
        print(f"  warning [{finding.rule}] {finding.message} ({', '.join(finding.fields)})")

    Path(REPORT_PATH).write_bytes(report.file)
    print(f"Saved the validation report to {REPORT_PATH} (valid: {report.valid}).")


if __name__ == "__main__":
    main()
