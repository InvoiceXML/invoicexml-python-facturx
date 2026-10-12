"""Generate the invoice model module from the InvoiceXML OpenAPI schema.

    python tools/generate_models.py            # uses tools/openapi.json
    python tools/generate_models.py --fetch    # downloads the live schema first

Field names, nesting, required flags and number/date formats come from the
schema. Field descriptions come from tools/field-docs.json and, for the options,
from tools/generator-config.json.

The published schema describes a few properties less precisely than the API
serializes them. These wire-format corrections are applied here, in one place:

* CountryCode, CurrencyCode, VatCategoryCode, InvoiceTypeCode are documented as
  integers but travel as string codes ("DE", "EUR", "S", "380").
* PdfLanguage is documented as an integer but travels as "EN", "DE" or "FR".
* PaymentDetails.paymentMeansCode is untyped; it is a UNTDID 4461 string code.
* InvoiceDocument.notes is an untyped array; each entry is an InvoiceNote object
  ({ note, subjectCode }), and the API also accepts a bare string.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SPEC_PATH = HERE / "openapi.json"
SPEC_URL = "https://api.invoicexml.com/v1/openapi"

STRING_CODES = {
    "CountryCode": 'ISO 3166-1 alpha-2 country code, for example ``"DE"``.',
    "CurrencyCode": 'ISO 4217 currency code, for example ``"EUR"``.',
    "VatCategoryCode": 'UNTDID 5305 VAT category code, for example ``"S"`` (standard rate). See ``VatCategoryCode``.',
    "InvoiceTypeCode": 'UNTDID 1001 document type code, for example ``"380"`` (commercial invoice). See ``InvoiceTypeCode``.',
}

CLASS_DOCS = {
    "CreateInvoiceRequest": "Request body of the create endpoints: the invoice plus optional processing options.",
    "InvoiceDocument": "An EN 16931 invoice, the shared document model of every create and extract endpoint.",
    "InvoiceNote": "Invoice note: free text plus an optional UNTDID 4451 subject code.",
    "InvoiceOptions": "Optional rendering and processing settings. Defaults apply when omitted.",
    "SellerParty": "The seller.",
    "SellerPostalAddress": "Seller postal address.",
    "SellerContact": "Seller contact.",
    "SellerIdentifier": "Seller identifier with its optional scheme identifier.",
    "SellerLegalRegistration": "Seller legal registration identifier with its optional scheme identifier.",
    "SellerElectronicAddress": "Seller electronic address with its scheme identifier.",
    "BuyerParty": "The buyer.",
    "BuyerPostalAddress": "Buyer postal address.",
    "BuyerContact": "Buyer contact.",
    "BuyerIdentifier": "Buyer identifier with its optional scheme identifier.",
    "BuyerLegalRegistration": "Buyer legal registration identifier with its optional scheme identifier.",
    "BuyerElectronicAddress": "Buyer electronic address with its scheme identifier.",
    "PrecedingInvoiceReference": "Reference to a preceding invoice.",
    "DeliveryInformation": "Delivery information.",
    "DeliveryPostalAddress": "Deliver-to address.",
    "InvoicingPeriod": "Invoicing period.",
    "PaymentDetails": "Payment instructions and payment terms.",
    "DocumentLevelAllowance": "Document level allowance.",
    "DocumentLevelCharge": "Document level charge.",
    "DocumentTotals": "Document totals. Calculated from the lines when omitted.",
    "VatBreakdown": "VAT breakdown. Calculated from the lines when omitted.",
    "AdditionalSupportingDocument": "Additional supporting document, referenced or embedded.",
    "InvoiceLine": "Invoice line.",
    "InvoiceLinePeriod": "Invoice line period.",
    "LineAllowance": "Invoice line allowance.",
    "LineCharge": "Invoice line charge.",
    "PriceDetails": "Price details.",
    "LineVatInformation": "Line VAT information.",
    "ItemInformation": "Item information.",
    "ItemAttribute": "Item attribute: a name and a value.",
    "ItemStandardIdentifier": "Item standard identifier with its scheme identifier, for example a GTIN.",
    "ItemClassification": "Item classification identifier with scheme and scheme version.",
    "LineObjectIdentifier": "Invoice line object identifier with its scheme identifier.",
}

VAT_CATEGORY_CODES = [
    ("STANDARD_RATE", "S", "Standard rate."),
    ("ZERO_RATED", "Z", "Zero rated goods."),
    ("EXEMPT", "E", "Exempt from tax."),
    ("REVERSE_CHARGE", "AE", "VAT reverse charge."),
    ("INTRA_COMMUNITY_SUPPLY", "K", "VAT exempt for EEA intra-community supply of goods and services."),
    ("EXPORT_OUTSIDE_EU", "G", "Free export item, VAT not charged."),
    ("OUTSIDE_SCOPE", "O", "Services outside scope of tax."),
    ("CANARY_ISLANDS_IGIC", "L", "Canary Islands general indirect tax."),
    ("CEUTA_MELILLA_IPSI", "M", "Tax for production, services and importation in Ceuta and Melilla."),
]

INVOICE_TYPE_CODES = [
    ("PARTIAL_INVOICE", "326", "Partial invoice."),
    ("INVOICE", "380", "Commercial invoice."),
    ("CREDIT_NOTE", "381", "Credit note."),
    ("DEBIT_NOTE", "383", "Debit note."),
    ("CORRECTED_INVOICE", "384", "Corrected invoice."),
    ("PREPAYMENT_INVOICE", "386", "Prepayment invoice."),
    ("SELF_BILLED_INVOICE", "389", "Self-billed invoice."),
    ("PARTIAL_CONSTRUCTION_INVOICE", "875", "Partial construction invoice."),
    ("PARTIAL_FINAL_CONSTRUCTION_INVOICE", "876", "Partial final construction invoice."),
    ("FINAL_CONSTRUCTION_INVOICE", "877", "Final construction invoice."),
]

HEADER = "# Generated by tools/generate_models.py from the InvoiceXML OpenAPI schema. Do not edit by hand.\n"
CODE_PATTERN = re.compile(r"\bB[TG]-\d")


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def ref_name(prop: dict) -> str | None:
    if "$ref" in prop:
        return prop["$ref"].rsplit("/", 1)[-1]
    for key in ("oneOf", "anyOf", "allOf"):
        for item in prop.get(key, []):
            if "$ref" in item:
                return item["$ref"].rsplit("/", 1)[-1]
    return None


def types_of(prop: dict) -> list[str]:
    t = prop.get("type", [])
    return [x for x in ([t] if isinstance(t, str) else t) if x != "null"]


def prune(full: dict, roots: list[str]) -> dict:
    """Keep only the schemas reachable from the roots, without descriptions."""
    all_schemas = full["components"]["schemas"]
    keep: set[str] = set()

    def walk(name: str) -> None:
        if name in keep or name not in all_schemas:
            return
        keep.add(name)
        for ref in re.findall(r"#/components/schemas/(\w+)", json.dumps(all_schemas[name])):
            walk(ref)

    for root in roots:
        walk(root)

    def strip(value):
        if isinstance(value, list):
            return [strip(v) for v in value]
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if k == "description" and isinstance(v, str):
                    continue
                if k == "properties" and isinstance(v, dict):
                    out[k] = {p: strip(d) for p, d in v.items()}
                else:
                    out[k] = strip(v)
            return out
        return value

    return {
        "openapi": full["openapi"],
        "info": {"title": full["info"]["title"], "version": full["info"]["version"]},
        "components": {"schemas": {n: strip(all_schemas[n]) for n in sorted(keep)}},
    }


def main() -> None:
    config = json.loads((HERE / "generator-config.json").read_text(encoding="utf-8"))
    field_docs = json.loads((HERE / "field-docs.json").read_text(encoding="utf-8"))

    if "--fetch" in sys.argv:
        with urllib.request.urlopen(SPEC_URL, timeout=60) as response:
            SPEC_PATH.write_bytes(response.read())

    spec = prune(json.loads(SPEC_PATH.read_text(encoding="utf-8")), config["roots"])
    SPEC_PATH.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")

    schemas = copy.deepcopy(spec["components"]["schemas"])
    schemas["PaymentDetails"]["properties"]["paymentMeansCode"] = {"type": ["null", "string"]}
    schemas["InvoiceDocument"]["properties"]["notes"] = {
        "type": "array", "items": {"$ref": "#/components/schemas/InvoiceNote"}}
    schemas["InvoiceNote"] = {
        "type": "object", "required": ["note"],
        "properties": {"note": {"type": ["null", "string"]}, "subjectCode": {"type": ["null", "string"]}}}

    excluded = config.get("excludeProperties", {})
    enums = config.get("stringEnums", {})
    prop_docs = config.get("propertyDocs", {})

    def kind_of(owner: str, name: str, prop: dict) -> tuple[str, str]:
        """Returns (type annotation, serde kind expression)."""
        enum_cfg = enums.get(f"{owner}.{name}")
        if enum_cfg:
            if "array" in types_of(prop):
                return f"list[{enum_cfg['type']} | str]", f'("list", ("enum", "{enum_cfg["type"]}"))'
            return f"{enum_cfg['type']} | str", f'("enum", "{enum_cfg["type"]}")'
        ref = ref_name(prop)
        if ref:
            if ref in STRING_CODES:
                return "str", '"str"'
            if ref == "PdfLanguage":
                return "PdfLanguage | str", '("enum", "PdfLanguage")'
            return ref, f'("model", "{ref}")'
        t = types_of(prop)
        if "array" in t:
            item = prop.get("items", {"type": "string"})
            item_ref = ref_name(item)
            if item_ref == "InvoiceNote":
                return "list[InvoiceNote | str]", '("list", ("note",))'
            inner_type, inner_kind = kind_of(owner, name, item)
            return f"list[{inner_type}]", f'("list", {inner_kind})'
        if "number" in t:
            return "Number", '"decimal"'
        if "integer" in t:
            return "int", '"int"'
        if "boolean" in t:
            return "bool", '"bool"'
        if "string" in t:
            if prop.get("format") == "date":
                return "date | str", '"date"'
            if prop.get("format") == "byte":
                return "bytes", '"bytes"'
            return "str", '"str"'
        raise SystemExit(f"Unmapped type for {owner}.{name}: {prop}")

    def code_of(prop: dict) -> str | None:
        ref = ref_name(prop)
        return ref if ref in STRING_CODES else None

    # reachable schemas in dependency order (referenced classes first)
    order: list[str] = []
    seen: set[str] = set()

    def visit(name: str) -> None:
        if name in seen or name in STRING_CODES or name == "PdfLanguage":
            return
        seen.add(name)
        for p, d in schemas[name].get("properties", {}).items():
            if p in excluded.get(name, []):
                continue
            r = ref_name(d) or ref_name(d.get("items", {}))
            if r:
                visit(r)
        order.append(name)

    for root in config["roots"]:
        visit(root)

    out: list[str] = [HEADER, '"""EN 16931 invoice model used by the create and extract endpoints.\n\n'
                      'Generated from the InvoiceXML OpenAPI schema. Every field is optional in\n'
                      'Python; the API reports missing required fields as findings.\n"""\n\n'
                      "from __future__ import annotations\n\n"
                      "import enum\n"
                      "from dataclasses import dataclass\n"
                      "from datetime import date\n"
                      "from typing import ClassVar\n\n"
                      "from ._serde import FieldSpec, Model, Number\n\n\n"]

    exports: list[str] = ["Number"]

    def enum_block(name: str, doc: str, values: list[tuple[str, str, str]]) -> str:
        lines = [f"class {name}(str, enum.Enum):", f'    """{doc}"""', ""]
        for key, value, value_doc in values:
            lines.append(f'    {key} = "{value}"')
            if value_doc:
                lines.append(f'    """{value_doc}"""')
        return "\n".join(lines) + "\n\n\n"

    def constants_block(name: str, doc: str, values: list[tuple[str, str, str]]) -> str:
        lines = [f"class {name}:", f'    """{doc}"""', ""]
        for key, value, value_doc in values:
            lines.append(f'    {key} = "{value}"')
            lines.append(f'    """{value_doc}"""')
        return "\n".join(lines) + "\n\n\n"

    out.append(enum_block("PdfLanguage", "Language of the rendered invoice PDF template.",
                          [("EN", "EN", "English."), ("DE", "DE", "German."), ("FR", "FR", "French.")]))
    exports.append("PdfLanguage")
    for cfg in enums.values():
        values = [(k, v, cfg.get("valueDocs", {}).get(k, "")) for k, v in cfg["values"].items()]
        out.append(enum_block(cfg["type"], cfg["doc"], values))
        exports.append(cfg["type"])
    out.append(constants_block("VatCategoryCode", "UNTDID 5305 VAT category codes used by EN 16931.", VAT_CATEGORY_CODES))
    out.append(constants_block("InvoiceTypeCode", "UNTDID 1001 invoice type codes accepted by the API.", INVOICE_TYPE_CODES))
    exports += ["VatCategoryCode", "InvoiceTypeCode"]

    for name in order:
        schema = schemas[name]
        props = [(p, d) for p, d in schema.get("properties", {}).items() if p not in excluded.get(name, [])]
        is_record = "identifier" in schema.get("properties", {}) or name in ("ItemAttribute", "InvoiceNote")
        required = [r for r in schema.get("required", []) if any(p == r for p, _ in props)]
        if is_record:
            required = [r for r in required if "null" not in ([schema["properties"][r].get("type")]
                                                              if isinstance(schema["properties"][r].get("type"), str)
                                                              else schema["properties"][r].get("type", []))]
        doc = CLASS_DOCS.get(name, name + ".")
        if required:
            doc += "\n\n    Required by the API: " + ", ".join(f"``{snake(r)}``" for r in required) + "."
        decorator = "@dataclass" if is_record else "@dataclass(kw_only=True)"
        lines = [decorator, f"class {name}(Model):", f'    """{doc}\n    """' if "\n" in doc else f'    """{doc}"""', ""]
        specs = []
        for p, d in props:
            attr = snake(p)
            annotation, kind = kind_of(name, p, d)
            lines.append(f"    {attr}: {annotation} | None = None")
            parts = []
            text = prop_docs.get(f"{name}.{p}") or field_docs.get(name, {}).get(p)
            if text:
                parts.append(text)
            if code_of(d):
                parts.append(STRING_CODES[code_of(d)])
            if annotation == "bytes":
                parts.append("Sent and received as base64 in JSON.")
            if p in required:
                parts.append("Required.")
            if parts:
                lines.append(f'    """{" ".join(parts)}"""')
            specs.append(f'        FieldSpec("{attr}", "{p}", {kind}),')
        lines.append("")
        lines.append("    _FIELDS: ClassVar[tuple[FieldSpec, ...]] = (")
        lines.extend(specs)
        lines.append("    )")
        out.append("\n".join(lines) + "\n\n\n")
        exports.append(name)

    out.append("__all__ = [\n" + "".join(f'    "{e}",\n' for e in sorted(exports)) + "]\n")
    text = "".join(out).rstrip("\n") + "\n"
    if chr(0x2014) in text:
        raise SystemExit("Em dash in generated models")
    if CODE_PATTERN.search(text):
        raise SystemExit("Business term code in generated models")
    target = REPO / config["module"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {len(order)} models to {config['module']}")


if __name__ == "__main__":
    main()
