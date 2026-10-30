"""Invoice email delivery: the message to send and the API's answer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from ._serde import FieldSpec, Model


@dataclass(kw_only=True, repr=False)
class EmailMessage(Model):
    """The email that carries an invoice to its recipient.

    The sender must be on a domain added and verified on the Verified email
    domains page of your dashboard.
    """

    from_: str
    """The sender address, on one of your verified domains. Sent as ``from``."""
    to: str
    """The recipient's email address. One address."""
    from_name: str | None = None
    """Display name of the sender. At most 100 characters, no line breaks."""
    cc: list[str] | None = None
    """Addresses that receive a visible copy. ``cc`` and ``bcc`` hold at most 2 addresses together."""
    bcc: list[str] | None = None
    """Addresses that receive a hidden copy. ``cc`` and ``bcc`` hold at most 2 addresses together."""
    reply_to: str | None = None
    """The address replies go to, when it differs from the sender. Any domain."""
    subject: str | None = None
    """The subject, at most 200 characters, no line breaks. Defaults to the document type and its number."""
    message: str | None = None
    """Plain-text message, at most 10,000 characters. Defaults to a short English text naming the invoice."""

    _FIELDS: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("from_", "from", "str"),
        FieldSpec("from_name", "fromName", "str"),
        FieldSpec("to", "to", "str"),
        FieldSpec("cc", "cc", ("list", "str")),
        FieldSpec("bcc", "bcc", ("list", "str")),
        FieldSpec("reply_to", "replyTo", "str"),
        FieldSpec("subject", "subject", "str"),
        FieldSpec("message", "message", "str"),
    )

    def __post_init__(self) -> None:
        if isinstance(self.cc, str):
            self.cc = [self.cc]
        if isinstance(self.bcc, str):
            self.bcc = [self.bcc]

    def __repr__(self) -> str:
        """Hide every value, so printing or logging a message reveals no address or text."""
        return "EmailMessage(<hidden>)"


@dataclass
class EmailSendResult:
    """Result of an email call. The file itself does not come back."""

    status: str
    """``"accepted"``: handed over for delivery, not yet received by the recipient's server."""
    message_id: str
    """The message id of the sent email."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EmailSendResult:
        return cls(status=data.get("status") or "", message_id=data.get("messageId") or "")
