# InvoiceXML Factur-X client for Python

Create, validate, embed and extract **Factur-X** e-invoices from Python with the [InvoiceXML API](https://www.invoicexml.com). Build the invoice from typed EN 16931 dataclasses and get back a compliant Factur-X PDF/A-3, already validated against the official rule set and, on request, the French mandate's BR-FR rules.

- Python 3.10 or later, no dependencies outside the standard library
- Typed EN 16931 dataclasses generated from the API's OpenAPI schema
- All Factur-X profiles, from MINIMUM to EXTENDED
- Exact decimal amounts, never floats on the wire
- Rejected invoices surface the violated rules as typed findings
- Automatic retry on HTTP 429, honouring `Retry-After`

## Installation

```bash
pip install invoicexml-facturx
```

## Get an API key

Sign up at [invoicexml.com/account/signup](https://www.invoicexml.com/account/signup) for a 30-day free trial with 100 credits. No credit card is needed. The client reads the key from the `INVOICEXML_API_KEY` environment variable, or you pass it as `api_key`.

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
| `validate_facturx(pdf, *, rules=None)` | `POST /v1/validate/facturx` | `ValidationResult` |
| `embed_facturx(pdf, xml, *, skip_validation=False, rules=None)` | `POST /v1/embed/facturx` | Factur-X PDF/A-3 (`bytes`) |
| `extract_json(file)` | `POST /v1/extract/json` | `InvoiceDocument` |
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

## Errors, rate limits and retries

All exceptions extend `InvoiceXmlError`.

| Exception | When |
|---|---|
| `InvoiceValidationError` | HTTP 400 with rule findings |
| `AuthenticationError` | HTTP 401, the API key is missing or inactive |
| `PayloadTooLargeError` | HTTP 413, a file exceeds 20 MB |
| `RateLimitError` | HTTP 429 after the automatic retries |
| `InvoiceXmlApiError` | Any other error response, with `error_code` from `ErrorCode` |
| `InvoiceXmlConnectionError` | The API could not be reached |

On HTTP 429 the client waits for the `Retry-After` delay and retries, three times by default. Rate-limited requests consume no credits.

```python
client = FacturXClient(api_key, max_retries=5, max_retry_wait=30, timeout=60)
```

The client holds no connection state and is safe to share between threads. To send requests through `requests`, `httpx` or your own tracing, pass any object with a `send(request)` method as `transport`; see `invoicexml_facturx.transport`.

## Why InvoiceXML

- **Rule sets updated on their legal effective dates.** New Factur-X, BR-FR and EN 16931 rule versions go live on the API the day they take legal effect. The rules run on the server, so you never update this package or redeploy for a new rule version.
- **Validated before delivery.** Every document is checked against the official XSD and Schematron rules before it is returned.
- **Zero data retention.** Invoices are processed in memory and purged when the response is delivered. Nothing is stored or logged, and nothing is used for AI training.
- **Processing in Frankfurt.** All processing happens in the EU, in Frankfurt, Germany. See [invoicexml.com/trust](https://www.invoicexml.com/trust).
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
