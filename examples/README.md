# Examples

Small scripts, one per common task. Each one is a complete `main.py` you can read from top to bottom and adapt.

| Example | What it shows |
|---|---|
| [create_facturx_with_own_pdf](create_facturx_with_own_pdf/main.py) | Create a Factur-X invoice that keeps your own PDF layout, passed as a public URL (`pdf_url`). |
| [create_cii_and_embed](create_cii_and_embed/main.py) | Build a CII XML from your invoice data with `create_cii`, then embed it into a PDF you already have with `embed_facturx`. |
| [validate_invoices](validate_invoices/main.py) | Validate a Factur-X PDF, optionally against the French BR-FR rules, print every finding, and save the printable validation report. |
| [render_xml_to_pdf](render_xml_to_pdf/main.py) | Turn any invoice XML (CII, UBL or XRechnung) into a readable PDF. |
| [convert_ubl_to_facturx](convert_ubl_to_facturx/main.py) | Convert a UBL invoice XML into a Factur-X invoice. |
| [transform_to_facturx](transform_to_facturx/main.py) | Turn an ordinary PDF invoice into a Factur-X invoice. AI reads the PDF, so a person checks the result. |
| [parse_pdf_invoice](parse_pdf_invoice/main.py) | Read an ordinary PDF invoice, typed, scanned or photographed, into the invoice model with AI, and see how sure the read was per area. |
| [extract_json_and_attachments](extract_json_and_attachments/main.py) | Read a received Factur-X invoice as a typed `InvoiceDocument` and save its embedded attachments as a ZIP. |

## Run an example

1. Open the example's `main.py` and replace the values at the top: `YOUR_API_KEY` with your API key, and the file paths or URLs with your own. An example whose file is missing tells you which value to change.
2. From the repository root, install the library from this repository's source, then run the example:

```bash
pip install -e .
python examples/create_cii_and_embed/main.py
```

The examples use the library source in this repository, so they always match the code next to them. To use one in your own project, copy its `main.py` and install the package instead:

```bash
pip install invoicexml-facturx
```

Get an API key with the **30-day free trial: 100 credits, no credit card required** at [www.invoicexml.com/account/signup](https://www.invoicexml.com/account/signup). The calls use credits from your account, so run the examples with test data.
