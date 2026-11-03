# Changelog

## 0.4.0

- Add `create_cii`, which builds a plain CII XML from the invoice model, ready for `embed_facturx` to turn your own PDF into a Factur-X invoice.
- Add `create_ubl`, which builds a UBL XML in the profile set by the new `InvoiceOptions.profile` (`UblProfile`, Peppol BIS Billing 3.0 by default).
- Add `ErrorCode.TOTALS_MISMATCH` (4024), returned when a transformed PDF's amounts do not add up to its printed total.

## 0.3.0

- Add rendering of CII XML as PDF, conversion between formats, the Factur-X validation report and transform to Factur-X.
- Add email delivery: `email_facturx` and `email_embedded_facturx` send the invoice from your own verified domain.

## 0.2.0

- Add `despatch_advice_reference` (BT-16, the delivery note number) to `InvoiceDocument`.

## 0.1.1

- Link the website at https://www.invoicexml.com in the package metadata, the README and error messages.

## 0.1.0

First release.

- `FacturXClient` with create, validate, embed and extract calls for Factur-X.
- Optional French BR-FR rule set on create, validate and embed, and the official profile identifiers.
- EN 16931 dataclasses generated from the InvoiceXML OpenAPI schema, with exact decimal amounts.
- Typed validation results and rule findings on rejected create requests.
- Automatic retry on HTTP 429 with `Retry-After` support.
- No dependencies outside the standard library.
