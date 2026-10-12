"""Pluggable HTTP layer.

The client builds the complete request and handles retries and error mapping
itself, so a transport only moves bytes. The default :class:`UrllibTransport`
uses the standard library. Implement :class:`Transport` to route calls through
``requests`` or ``httpx``, add tracing, or stub the API in tests.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class TransportRequest:
    """An HTTP request as built by the client."""

    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes
    timeout: float

    def header(self, name: str) -> str | None:
        """Return a header value, matching the name case-insensitively."""
        for key, value in self.headers.items():
            if key.lower() == name.lower():
                return value
        return None


@dataclass(frozen=True)
class TransportResponse:
    """A raw HTTP response."""

    status_code: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""

    def header(self, name: str) -> str | None:
        """Return a header value, matching the name case-insensitively."""
        for key, value in self.headers.items():
            if key.lower() == name.lower():
                return value
        return None


class Transport(Protocol):
    """Sends one request and returns the response, whatever its status code.

    Raise ``OSError`` (for example ``ConnectionError`` or ``TimeoutError``) when
    no response was received.
    """

    def send(self, request: TransportRequest) -> TransportResponse: ...


class UrllibTransport:
    """:class:`Transport` backed by ``urllib.request``. Honours the standard proxy variables."""

    def send(self, request: TransportRequest) -> TransportResponse:
        req = urllib.request.Request(request.url, data=request.body, method=request.method,
                                     headers=dict(request.headers))
        try:
            with urllib.request.urlopen(req, timeout=request.timeout) as response:
                return TransportResponse(response.status, dict(response.headers.items()), response.read())
        except urllib.error.HTTPError as error:
            with error:
                body = error.read()
            return TransportResponse(error.code, dict(error.headers.items()) if error.headers else {}, body)
        except urllib.error.URLError as error:
            raise ConnectionError(str(error.reason)) from error
