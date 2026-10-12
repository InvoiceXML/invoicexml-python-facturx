# Changelog

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
