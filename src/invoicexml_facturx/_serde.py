"""Mapping between the dataclass models and the API's JSON."""

from __future__ import annotations

import base64
import enum
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar, TypeVar, Union

Number = Union[Decimal, int, float, str]
"""A monetary amount, quantity or rate. Pass a ``Decimal`` or a string for exact
values; floats are converted through their shortest text form."""

M = TypeVar("M", bound="Model")


@dataclass(frozen=True)
class FieldSpec:
    """How one dataclass attribute maps to its JSON property."""

    attr: str
    json: str
    kind: Any


class Model:
    """Base class of the generated invoice models."""

    _FIELDS: ClassVar[tuple[FieldSpec, ...]] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-ready representation, without unset fields."""
        out: dict[str, Any] = {}
        for spec in self._FIELDS:
            value = getattr(self, spec.attr)
            if value is not None:
                out[spec.json] = _dump(spec.kind, value, self)
        return out

    @classmethod
    def from_dict(cls: type[M], data: Mapping[str, Any]) -> M:
        """Build an instance from API JSON. Unknown properties are ignored."""
        kwargs = {}
        for spec in cls._FIELDS:
            value = data.get(spec.json)
            if value is not None:
                kwargs[spec.attr] = _load(spec.kind, value, cls)
        return cls(**kwargs)


def _resolve(owner: Any, name: str) -> Any:
    return getattr(sys.modules[owner.__module__], name)


def _dump(kind: Any, value: Any, owner: Any) -> Any:
    if isinstance(kind, tuple):
        tag = kind[0]
        if tag == "list":
            return [_dump(kind[1], item, owner) for item in value]
        if tag == "model":
            return value.to_dict() if isinstance(value, Model) else dict(value)
        if tag == "enum":
            return value.value if isinstance(value, enum.Enum) else str(value)
        if tag == "note":
            if isinstance(value, str):
                return {"note": value}
            return value.to_dict() if isinstance(value, Model) else dict(value)
        raise TypeError(f"Unknown field kind {kind!r}")
    if kind == "decimal":
        return to_decimal(value)
    if kind == "date":
        return value.isoformat() if isinstance(value, (date, datetime)) else str(value)
    if kind == "bytes":
        return base64.b64encode(bytes(value)).decode("ascii")
    if kind == "str" and isinstance(value, enum.Enum):
        return value.value
    return value


def _load(kind: Any, value: Any, owner: Any) -> Any:
    if isinstance(kind, tuple):
        tag = kind[0]
        if tag == "list":
            return [_load(kind[1], item, owner) for item in value]
        if tag == "model":
            return _resolve(owner, kind[1]).from_dict(value)
        if tag == "enum":
            try:
                return _resolve(owner, kind[1])(value)
            except ValueError:
                return value
        if tag == "note":
            note_cls = _resolve(owner, "InvoiceNote")
            return note_cls(note=value) if isinstance(value, str) else note_cls.from_dict(value)
        raise TypeError(f"Unknown field kind {kind!r}")
    if kind == "decimal":
        return to_decimal(value)
    if kind == "date":
        return date.fromisoformat(str(value)[:10])
    if kind == "bytes":
        return base64.b64decode(value)
    return value


def to_decimal(value: Any) -> Decimal:
    """Convert a number-like value to ``Decimal`` without float noise."""
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, bool):
        raise TypeError("A boolean is not a number")
    elif isinstance(value, (int, float, str)):
        result = Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
    else:
        raise TypeError(f"Expected a number, got {type(value).__name__}")
    if not result.is_finite():
        raise ValueError(f"Not a finite number: {value!r}")
    return result


def dumps(value: Any) -> str:
    """Serialize to JSON, writing ``Decimal`` values as exact JSON numbers."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Mapping):
        return "{" + ",".join(json.dumps(str(k)) + ":" + dumps(v) for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(dumps(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def loads(data: bytes | str) -> Any:
    """Parse JSON, reading fractional numbers as ``Decimal``."""
    return json.loads(data, parse_float=Decimal)
