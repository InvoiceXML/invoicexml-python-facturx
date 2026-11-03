# InvoiceXML Factur-X client for Python

Create, validate, embed, render, convert and extract **Factur-X** e-invoices from Python with the [InvoiceXML API](https://www.invoicexml.com). Build the invoice from typed EN 16931 dataclasses and get back a compliant Factur-X PDF/A-3, already validated against the official rule set and, on request, the French mandate's BR-FR rules.

- Python 3.10 or later, no dependencies outside the standard library
- Typed EN 16931 dataclasses generated from the API's OpenAPI schema
- All Factur-X profiles, from MINIMUM to EXTENDED
- Exact decimal amounts, never floats on the wire
- Rejected invoices surface the violated rules as typed findings
- Automatic retry on HTTP 429 on every call except transform and parse, honouring `Retry-After`

## Installation

```bash
pip install invoicexml-facturx
```

## Get an API key

Sign up at [www.invoicexml.com/account/signup](https://www.invoicexml.com/account/signup) for a 30-day free trial with 100 credits. No credit card is needed. The client reads the key from the `INVOICEXML_API_KEY` environment variable, or you pass it as `api_key`.

## Create a Factur-X invoice

```python
from pathlib import Path
from invoicexml_facturx import *

client = FacturXClient()
invoice = InvoiceDocument(
    invoice_number="FA-2026-0042", issue_date="2026-09-01", currency="EUR",
    seller=SellerParty(name="Atelier Numerique SARL", vat_identifier="FR32123456789",
                       legal_registration=SellerLegalRegistration("123456789", "0002"),
                       postal_address=SellerPostalAddress(line1="18 Rue de la Republique", city="Lyon", post_code="69002", country="FR")),
    buyer=BuyerParty(name="Librairie Grand Siecle SAS",
                     postal_address=BuyerPostalAddress(line1="5 Boulevard Saint-Germain", city="Paris", post_code="75005", country="FR")),
    payment_details=PaymentDetails(payment_account_identifier="FR7630006000011234567890189"),
    lines=[InvoiceLine(quantity=12, item=ItemInformation(name="Maintenance applicative"),
                       price_details=PriceDetails(net_price="180.00"), vat_information=LineVatInformation(rate=20))],
)
Path("facture-facturx.pdf").write_bytes(client.create_facturx(invoice, InvoiceOptions(language=PdfLanguage.FR)))
```

Totals and the VAT breakdown are calculated from the lines. The PDF is a Factur-X PDF/A-3 with the EN 16931 profile and the CII XML embedded as `factur-x.xml`. Amounts accept `Decimal`, `int`, `float` or a numeric string, and are sent as exact JSON numbers.

## API surface

| Method | Endpoint | Returns |
|---|---|---|
| `create_facturx(invoice, options=None)` | `POST /v1/create/facturx` | Factur-X PDF/A-3 (`bytes`) |
| `create_cii(invoice, options=None)` | `POST /v1/create/cii` | CII XML (`str`) |
| `create_ubl(invoice, options=None)` | `POST /v1/create/ubl` | UBL XML (`str`) |
| `validate_facturx(pdf, *, rules=None)` | `POST /v1/validate/facturx` | `ValidationResult` |
| `validate_facturx_report(pdf, *, rules=None, validation_language=None)` | `POST /v1/validate/facturx/report` | `ValidationReport` |
| `embed_facturx(pdf, xml, *, skip_validation=False, rules=None)` | `POST /v1/embed/facturx` | Factur-X PDF/A-3 (`bytes`) |
| `email_facturx(invoice, email, options=None)` | `POST /v1/create/facturx/email` | `EmailSendResult` |
| `email_embedded_facturx(pdf, xml, email, *, rules=None)` | `POST /v1/embed/facturx/email` | `EmailSendResult` |
| `render_xml_to_pdf(xml, *, language=None, logo_url=None, include_qr_code=None)` | `POST /v1/render/xml/to/pdf` | Readable PDF (`bytes`) |
| `convert_facturx_to_ubl(pdf, *, validation_language=None)` | `POST /v1/convert/facturx/to/ubl` | UBL XML (`str`) |
| `convert_facturx_to_cii(pdf, *, validation_language=None)` | `POST /v1/convert/facturx/to/cii` | CII XML (`str`) |
| `convert_cii_to_facturx(xml, *, language=None, validation_language=None)` | `POST /v1/convert/cii/to/facturx` | Factur-X PDF/A-3 (`bytes`) |
| `convert_ubl_to_facturx(xml, *, language=None, validation_language=None)` | `POST /v1/convert/ubl/to/facturx` | Factur-X PDF/A-3 (`bytes`) |
| `convert_xrechnung_to_facturx(xml, *, language=None, validation_language=None)` | `POST /v1/convert/xrechnung/to/facturx` | Factur-X PDF/A-3 (`bytes`) |
| `transform_to_facturx(pdf, *, language=None, preserve_original_pdf=None, include_advanced_properties=None, validation_language=None)` | `POST /v1/transform/to/facturx` | Factur-X PDF/A-3 (`bytes`), to be checked by a person |
| `extract_json(file)` | `POST /v1/extract/json` | `InvoiceDocument` |
| `parse_json(file)` | `POST /v1/parse/json` | `ParsedInvoice`, to be checked by a person |
| `extract_attachments(file)` | `POST /v1/extract/attachments` | ZIP of embedded documents (`bytes`) |

File parameters accept a path, the raw bytes of a PDF or XML document, or a `FileUpload`. The invoice and options also accept plain dicts in the API's JSON shape.

## The French e-invoicing mandate

Receiving e-invoices is mandatory for every business in France from September 2026, and issuing follows in phases. Add the `BR_FR` rule set to check an invoice against the mandate's BR-FR rules on top of its profile. It works on create, validate and embed, and needs at least the BASIC profile:

```python
invoice.business_process_type = "S1"                    # billing mode, here services
invoice.notes = [InvoiceNote("Indemnite forfaitaire pour frais de recouvrement : 40 EUR", "PMT")]
pdf = client.create_facturx(invoice, InvoiceOptions(rules=[RuleSet.BR_FR]))

result = client.validate_facturx("facture.pdf", rules=[RuleSet.BR_FR])
```

The BR-FR rules ask for the billing mode in `business_process_type`, for example `B1` for goods, `S1` for services or `M1` for mixed invoices. French invoices also carry the legal mentions as notes with the subject codes `PMT`, `PMD` and `AAB`. Violations come back with the official rule identifiers and French messages.

## Profiles

EN 16931 is the default. To create another profile, set its identifier from `FacturXProfile` as the invoice's `specification_id`:

```python
invoice.specification_id = FacturXProfile.BASIC
pdf = client.create_facturx(invoice)
```

`MINIMUM` and `BASIC_WL` carry header data only and serve as booking aids. `BASIC` is the lowest profile the French mandate accepts, and `EXTENDED` adds data for complex invoicing.

## Use your own PDF layout

To keep the PDF your own system prints, create the CII XML from the same invoice object and embed it into that PDF. The XML declares the EN 16931 profile, so `embed_facturx` takes it as is:

```python
xml = client.create_cii(invoice, InvoiceOptions(rules=[RuleSet.BR_FR], language=PdfLanguage.FR))
pdf = client.embed_facturx("my-invoice.pdf", FileUpload.xml(xml), rules=[RuleSet.BR_FR])
```

`language` sets the default texts written into the XML, such as the payment terms. See the [create CII guide](https://www.invoicexml.com/docs/api/create/cii).

## Create a UBL invoice

`create_ubl` builds a UBL 2.1 XML from the same invoice object, validated against the rule set of the profile you pick (Peppol BIS Billing 3.0 when omitted, see the [create UBL reference](https://www.invoicexml.com/docs/api/create/ubl)):

```python
xml = client.create_ubl(invoice, InvoiceOptions(profile=UblProfile.PEPPOL_BIS_3))
```

## Send an invoice by email

Create the invoice and have it emailed to the recipient in one call, from your own domain. The invoice is validated exactly like on the create call:

```python
email = EmailMessage(from_="factures@votreentreprise.fr", to="client@example.com", from_name="Votre Entreprise",
                     cc=["compta@votreentreprise.fr"], subject="Facture FA-2026-0042")
result = client.email_facturx(invoice, email)
print(result.status, result.message_id)
```

`email_embedded_facturx("facture.pdf", "facture.xml", email)` embeds your XML into your PDF first, always with full validation, and takes the same `rules` as `embed_facturx`. These calls send a real email and return the message id, not the file. The status `accepted` means the email was handed over for delivery, not yet that the recipient's server received it.

The sender must be on a domain added and verified on the Verified email domains page of your dashboard. `cc` and `bcc` hold at most 2 addresses together. See the [email guide](https://www.invoicexml.com/docs/api/create/facturx/email).

An unverified sender domain raises `InvoiceXmlApiError` with `ErrorCode.EMAIL_DOMAIN_NOT_VERIFIED`, `EMAIL_NOT_IN_PLAN` means [your plan does not include this](https://www.invoicexml.com/pricing), and `EMAIL_SENDING_DISABLED` means sending is disabled or paused for your account. None of these consume credits. A bad address raises `InvoiceValidationError` with the affected `email.*` field.

Only HTTP 429 is retried, because nothing was sent. Other failures are never retried, since a second attempt could send a second email. After a timeout or a connection failure the outcome is unknown, so check before you send it again.

## Rejected invoices

Every create call validates the invoice before a document is produced. When rules are violated, the call raises `InvoiceValidationError` with the findings, so a non-compliant invoice never leaves your system:

```python
try:
    client.create_facturx(invoice)
except InvoiceValidationError as e:
    for finding in e.errors:
        print(finding.rule, finding.fields, finding.message)
```

Each finding carries the rule id (for example `BR-CO-10`), the layer (`xsd`, `en16931` or `cius`), a plain-language message, the field paths into your invoice, and the verbatim validator output.

## Validate incoming invoices

Valid and invalid invoices both return a `ValidationResult`. Check `result.valid`:

```python
result = client.validate_facturx("facture-fournisseur.pdf")
if not result.valid:
    for finding in result.errors:
        print(finding)
```

The result also carries the detected profile, the schema and Schematron verdicts, and a field report with one row per invoice field.

## Validation report

`validate_facturx_report` runs the same checks and returns a printable PDF report with the verdict. It takes the same `rules` as `validate_facturx`, and `validation_language` words the whole report in `en`, `de` or `fr`:

```python
report = client.validate_facturx_report("facture-fournisseur.pdf", rules=[RuleSet.BR_FR], validation_language="fr")
Path("rapport.pdf").write_bytes(report.file)
if report.valid is False:
    print("Not compliant, see the report")
```

A failed verdict is a normal result, not an exception. `report.valid` is `True`, `False`, or `None` when the response carried no verdict. A missing or malformed file still raises the usual error. See the [report guide](https://www.invoicexml.com/docs/api/validate/facturx/report).

## Render an invoice as PDF

Turn any invoice XML into a readable PDF, for a preview or for people who cannot read XML. CII (such as the XML of a Factur-X invoice), UBL and XRechnung are all accepted, and the format is detected from the XML:

```python
pdf = client.render_xml_to_pdf("facture.xml", language=PdfLanguage.FR, include_qr_code=True,
                               logo_url="https://example.com/logo.png")
```

`language` picks `en`, `de` or `fr`, and `include_qr_code` prints the payment QR code. See the [render guide](https://www.invoicexml.com/docs/api/render/xml/to/pdf).

## Convert between formats

Each conversion has its own method. `convert_facturx_to_ubl` and `convert_facturx_to_cii` return the XML as `str`, and the routes to Factur-X return the PDF/A-3 as `bytes`:

```python
ubl = client.convert_facturx_to_ubl("facture.pdf")
Path("facture-facturx.pdf").write_bytes(client.convert_cii_to_facturx("facture.xml", language=PdfLanguage.FR))
```

The result is validated like a created document, so a conversion that violates the rules raises `InvoiceValidationError`, with the findings worded in `validation_language` (`en`, `de` or `fr`). `language` is only taken by the routes to Factur-X, where it sets the language of the rendered PDF. See the guides: [Factur-X to UBL](https://www.invoicexml.com/docs/api/convert/facturx/to/ubl), [Factur-X to CII](https://www.invoicexml.com/docs/api/convert/facturx/to/cii), [CII to Factur-X](https://www.invoicexml.com/docs/api/convert/cii/to/facturx), [UBL to Factur-X](https://www.invoicexml.com/docs/api/convert/ubl/to/facturx) and [XRechnung to Factur-X](https://www.invoicexml.com/docs/api/convert/xrechnung/to/facturx).

## Transform a PDF invoice

`transform_to_facturx` has AI read a PDF invoice and builds the Factur-X from what it read, so a person must check the result before it is used:

```python
pdf = client.transform_to_facturx("facture.pdf")
```

By default the PDF is rendered from the data the AI read, in the language of the invoice, and ends with an "Electronic invoice details" section, so the data can be checked on the pages. `language` takes `en`, `de`, `fr` or `auto`, the default. Set `include_advanced_properties=False` to leave that section out, or `preserve_original_pdf=True` to keep the uploaded PDF as the visual layer. A 429 on this method is not retried automatically, so wait for `Retry-After` before calling again if you want to retry. See the [transform guide](https://www.invoicexml.com/docs/api/transform/to/facturx).

## Read a PDF invoice with AI

`parse_json` has AI read a typed, scanned or photographed PDF invoice into the invoice model, with a confidence score per area and the language the invoice is written in. A person must check the data before it is used, and an XML embedded in the PDF is ignored (`extract_json` reads that):

```python
parsed = client.parse_json("facture-scannee.pdf")
print(parsed.invoice.invoice_number, parsed.language)
if parsed.confidence:
    print(parsed.confidence.overall, parsed.confidence.areas.line_items)
```

Scores run from 0 (had to guess) to 1 (unambiguous). `language` is a lowercase ISO 639-1 code, or `None` when it could not be told. Any language can come back, so it is not always a `PdfLanguage` the create and render methods take. A 429 on this method is not retried automatically. See the [parse guide](https://www.invoicexml.com/docs/api/parse/json).

## Errors, rate limits and retries

All exceptions extend `InvoiceXmlError`.

| Exception | When |
|---|---|
| `InvoiceValidationError` | HTTP 400 with rule findings |
| `AuthenticationError` | HTTP 401, the API key is missing or inactive |
| `PayloadTooLargeError` | HTTP 413, a file exceeds 20 MB |
| `RateLimitError` | HTTP 429 after any automatic retries |
| `InvoiceXmlApiError` | Any other error response, with `error_code` from `ErrorCode` |
| `InvoiceXmlConnectionError` | The API could not be reached |

On HTTP 429 every call except transform and parse waits for the `Retry-After` delay and retries, three times by default. A 429 is not billed.

```python
client = FacturXClient(api_key, max_retries=5, max_retry_wait=30, timeout=60)
```

The client holds no connection state and is safe to share between threads. To send requests through `requests`, `httpx` or your own tracing, pass any object with a `send(request)` method as `transport`; see `invoicexml_facturx.transport`.

## Examples

The [examples](https://github.com/InvoiceXML/invoicexml-python-facturx/tree/main/examples) folder has one runnable script per common task: create a Factur-X invoice with your own PDF, create a CII and embed it, validate, render, convert, transform, parse with AI, and extract. Each one is a complete `main.py` you can read from top to bottom and adapt.

## Why InvoiceXML

- **Rule sets updated on their legal effective dates.** New Factur-X, BR-FR and EN 16931 rule versions go live on the API the day they take legal effect. The rules run on the server, so you never update this package or redeploy for a new rule version.
- **Validated before delivery.** Every document is checked against the official XSD and Schematron rules before it is returned.
- **Zero data retention.** Invoices are processed in memory and purged when the response is delivered. Nothing is stored or logged, and nothing is used for AI training. When you email an invoice, it goes to our email service for delivery, and we keep no copy.
- **Processing in Frankfurt.** All processing happens in the EU, in Frankfurt, Germany. See [www.invoicexml.com/trust](https://www.invoicexml.com/trust).
- **Integration assistance.** Questions about your integration go to [support@invoicexml.com](mailto:support@invoicexml.com), from setup to your first production invoice.

## Documentation

- API reference: [api.invoicexml.com/v1/scalar](https://api.invoicexml.com/v1/scalar/)
- OpenAPI 3.1 schema: [api.invoicexml.com/v1/openapi](https://api.invoicexml.com/v1/openapi)
- ZUGFeRD and XRechnung: see the companion package [invoicexml-zugferd-xrechnung](https://github.com/InvoiceXML/invoicexml-python-zugferd-xrechnung)

## Development

```bash
pip install pytest
pytest
```

The unit tests run against a stubbed HTTP layer. A live suite against the real API runs only when you opt in, and it consumes about 13 credits per run:

```bash
INVOICEXML_API_KEY=your-key INVOICEXML_LIVE=1 pytest -m live
```

The module `invoicexml_facturx/models.py` is generated from the OpenAPI schema. To refresh it after a schema change, run `python tools/generate_models.py --fetch` and commit the result.

## License

MIT. See [LICENSE](LICENSE).
