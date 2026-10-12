"""File inputs for the upload endpoints."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Union

APPLICATION_PDF = "application/pdf"
APPLICATION_XML = "application/xml"
APPLICATION_OCTET_STREAM = "application/octet-stream"


@dataclass(frozen=True)
class FileUpload:
    """A file to upload: name, content and media type.

    The API recognises PDFs and XML files by media type or file extension. The
    upload methods also accept a path or raw bytes directly, so you rarely need
    this class:

    >>> FileUpload.from_path("invoice.pdf")       # type from the extension
    >>> FileUpload.pdf(pdf_bytes)                 # "invoice.pdf", application/pdf
    >>> FileUpload.xml(xml_text)                  # "invoice.xml", application/xml

    Files up to 20 MB are accepted.
    """

    file_name: str
    content: bytes
    content_type: str = APPLICATION_OCTET_STREAM

    @classmethod
    def from_path(cls, path: str | os.PathLike[str]) -> FileUpload:
        """Read a file from disk. The media type is inferred from the extension."""
        p = Path(path)
        return cls(p.name, p.read_bytes(), _content_type_for(p.name))

    @classmethod
    def pdf(cls, content: bytes, file_name: str = "invoice.pdf") -> FileUpload:
        """A PDF upload."""
        return cls(file_name, bytes(content), APPLICATION_PDF)

    @classmethod
    def xml(cls, content: bytes | str, file_name: str = "invoice.xml") -> FileUpload:
        """An XML upload. Text is encoded as UTF-8."""
        data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        return cls(file_name, data, APPLICATION_XML)

    def __repr__(self) -> str:
        return f"FileUpload({self.file_name!r}, {self.content_type!r}, {len(self.content)} bytes)"


FileInput = Union[FileUpload, str, os.PathLike, bytes, bytearray]
"""A path, raw bytes (a PDF or XML document, detected from the content), or a :class:`FileUpload`."""


def _content_type_for(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".pdf"):
        return APPLICATION_PDF
    if lower.endswith(".xml"):
        return APPLICATION_XML
    return APPLICATION_OCTET_STREAM


def to_upload(value: FileInput) -> FileUpload:
    """Normalise any accepted file input to a :class:`FileUpload`."""
    if isinstance(value, FileUpload):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        head = data[:1024].lstrip(b"\xef\xbb\xbf \t\r\n")
        if head.startswith(b"%PDF"):
            return FileUpload.pdf(data)
        if head.startswith(b"<"):
            return FileUpload.xml(data)
        return FileUpload("upload", data)
    if isinstance(value, (str, os.PathLike)):
        return FileUpload.from_path(value)
    raise TypeError(f"Expected a path, bytes or FileUpload, got {type(value).__name__}")
