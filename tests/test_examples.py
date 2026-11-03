"""The examples only use names, keywords, model fields and enum members this package provides,
so they cannot fall behind it.

Each example's ``main()`` runs against a stub transport, with throwaway input files and fake
responses: once on the happy path, once with its input file missing, and once per error branch.
No request reaches the API.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

import invoicexml_facturx as package
from conftest import StubTransport, fixture
from invoicexml_facturx import FacturXClient
from invoicexml_facturx.transport import UrllibTransport

EXAMPLES = sorted((Path(__file__).resolve().parent.parent / "examples").glob("*/main.py"))
API_KEY = "YOUR_API_KEY"
BASE_URL = "https://api.invoicexml.com"

PDF = b"%PDF-1.7 stub"
XML = '<?xml version="1.0"?><rsm:CrossIndustryInvoice/>'
ZIP = b"PK\x05\x06" + b"\x00" * 18

# Constants naming a file the example writes. Every other *_PATH constant names a file it reads.
OUTPUTS = ("OUTPUT_PATH", "REPORT_PATH", "ATTACHMENTS_ZIP_PATH")

Respond = Callable[[StubTransport], StubTransport]


def pdf(stub: StubTransport) -> StubTransport:
    return stub.respond(200, PDF, "application/pdf")


def xml(stub: StubTransport) -> StubTransport:
    return stub.respond(200, XML, "application/xml")


def extracted(stub: StubTransport) -> StubTransport:
    return stub.respond_json(200, fixture("extract-json.json"))


def parsed(stub: StubTransport) -> StubTransport:
    payload = json.loads(fixture("extract-json.json"))
    payload["confidence"] = {"overall": 0.83, "areas": {"sellerIdentification": 1, "buyerIdentification": 0.9,
                                                        "taxCalculation": None, "lineItems": 0.6}}
    payload["language"] = "fr"
    return stub.respond_json(200, payload)


def validated(stub: StubTransport) -> StubTransport:
    return stub.respond_json(200, fixture("validate-facturx-invalid.json"))


def report(stub: StubTransport) -> StubTransport:
    return stub.respond(200, PDF, "application/pdf", X_Invoice_Valid="false")


def attachments(stub: StubTransport) -> StubTransport:
    return stub.respond(200, ZIP, "application/zip")


# The calls each example makes on the happy path, in order, with the response each one gets.
CALLS: dict[str, list[tuple[str, Respond]]] = {
    "convert_ubl_to_facturx": [("/v1/convert/ubl/to/facturx", pdf)],
    "create_cii_and_embed": [("/v1/create/cii", xml), ("/v1/embed/facturx", pdf)],
    "create_facturx_with_own_pdf": [("/v1/create/facturx", pdf)],
    "extract_json_and_attachments": [("/v1/extract/json", extracted), ("/v1/extract/attachments", attachments)],
    "parse_pdf_invoice": [("/v1/parse/json", parsed)],
    "render_xml_to_pdf": [("/v1/render/xml/to/pdf", pdf)],
    "transform_to_facturx": [("/v1/transform/to/facturx", pdf)],
    "validate_invoices": [("/v1/validate/facturx", validated), ("/v1/validate/facturx/report", report)],
}


def problem(status: int, code: int, **extra: object) -> Respond:
    def respond(stub: StubTransport) -> StubTransport:
        headers = {"Retry_After": "7"} if status == 429 else {}
        return stub.respond_json(status, {"title": "Refused", "status": status, "errorCode": code, **extra}, **headers)
    return respond


def invalid(stub: StubTransport) -> StubTransport:
    return stub.respond_json(400, fixture("create-400.json"))


# Answers that send the examples down their error branches.
ERRORS: dict[str, Respond] = {
    "invalid": invalid,
    "rate-limited": problem(429, 4019),
    "totals-mismatch": problem(400, 4024, errors=[{"rule": "TOTALS-MISMATCH", "message": "Totals do not add up.",
                                                   "fields": []}]),
    "domain-not-verified": problem(400, 4022),
    "no-attachments": problem(400, 4013),
    "unauthorized": problem(401, 4010),
}


def name(path: Path) -> str:
    return path.parent.name


def inputs(path: Path) -> list[str]:
    found = re.findall(r"^(\w+_PATH) = ", path.read_text(encoding="utf-8"), flags=re.MULTILINE)
    return [constant for constant in found if constant not in OUTPUTS]


def load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"example_{name(path)}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def outputs(module: ModuleType) -> list[str]:
    return [getattr(module, constant) for constant in OUTPUTS if hasattr(module, constant)]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(self, request):
        raise AssertionError(f"An example tried to reach the network: {request.url}")
    monkeypatch.setattr(UrllibTransport, "send", refuse)


def run(path: Path, stub: StubTransport, tmp_path: Path, monkeypatch, capsys, *, with_inputs: bool = True) -> str:
    """Runs the example's main() in tmp_path, with its client on the stub and its inputs on throwaway files."""
    module = load(path)
    monkeypatch.chdir(tmp_path)

    def create_client(api_key: str, **kwargs) -> FacturXClient:
        assert api_key == API_KEY
        return FacturXClient(api_key, transport=stub, max_retries=0, **kwargs)

    monkeypatch.setattr(module, FacturXClient.__name__, create_client)
    if with_inputs:
        for constant in inputs(path):
            if "XML" in constant:
                target = tmp_path / "input.xml"
                target.write_text(XML, encoding="utf-8")
            else:
                target = tmp_path / "input.pdf"
                target.write_bytes(PDF)
            monkeypatch.setattr(module, constant, str(target))

    module.main()
    return capsys.readouterr().out


def test_every_example_is_found():
    assert len(EXAMPLES) == 8
    assert sorted(CALLS) == [name(path) for path in EXAMPLES]


@pytest.mark.parametrize("path", EXAMPLES, ids=name)
def test_example_compiles_and_uses_only_existing_names(path: Path):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    compile(tree, str(path), "exec")

    imported = [alias.name for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module == package.__name__ for alias in node.names]
    assert imported, "the example imports the package"
    assert [name for name in imported if not hasattr(package, name)] == []

    called = {node.attr for node in ast.walk(tree)
              if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "client"}
    assert called, "the example calls the client"
    assert [name for name in called if not hasattr(FacturXClient, name)] == []

    assert f'API_KEY = "{API_KEY}"' in source


@pytest.mark.parametrize("path", EXAMPLES, ids=name)
def test_example_runs_on_the_happy_path(path: Path, stub, tmp_path, monkeypatch, capsys):
    calls = CALLS[name(path)]
    for _, respond in calls:
        respond(stub)

    out = run(path, stub, tmp_path, monkeypatch, capsys)

    assert [request.url.removeprefix(BASE_URL) for request in stub.requests] == [route for route, _ in calls]
    assert "refused" not in out and "Could not find" not in out
    assert [output for output in outputs(load(path)) if not (tmp_path / output).exists()] == []


@pytest.mark.parametrize("path", [path for path in EXAMPLES if inputs(path)], ids=name)
def test_example_stops_before_any_call_when_its_input_is_missing(path: Path, stub, tmp_path, monkeypatch, capsys):
    out = run(path, stub, tmp_path, monkeypatch, capsys, with_inputs=False)

    assert "Could not find" in out
    assert stub.requests == []


@pytest.mark.parametrize(("path", "failing", "error"), [
    pytest.param(path, failing, error, id=f"{name(path)}-call{failing + 1}-{error}")
    for path in EXAMPLES for failing in range(len(CALLS[name(path)])) for error in ERRORS
])
def test_example_handles_every_error(path: Path, failing: int, error: str, stub, tmp_path, monkeypatch, capsys):
    for _, respond in CALLS[name(path)][:failing]:
        respond(stub)
    ERRORS[error](stub)

    out = run(path, stub, tmp_path, monkeypatch, capsys)

    assert len(stub.requests) == failing + 1, "the example stops at the failed call"
    assert out.strip()
    assert [output for output in outputs(load(path)) if (tmp_path / output).exists()] == []


def test_parse_example_prints_a_dash_for_a_missing_overall_score(stub, tmp_path, monkeypatch, capsys):
    path = next(path for path in EXAMPLES if name(path) == "parse_pdf_invoice")
    payload = json.loads(fixture("extract-json.json"))
    payload["confidence"] = {"overall": None, "areas": {}}
    stub.respond_json(200, payload)

    out = run(path, stub, tmp_path, monkeypatch, capsys)

    assert "Confidence overall: -\n" in out
