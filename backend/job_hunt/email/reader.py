"""Read-only IMAP email reader — stdlib only, zero new dependencies.

Provides a context-manager IMAP connection, mailbox selection, UID-based
incremental fetch with BODY.PEEK (never sets \\Seen), and pure helpers for
extracting plain text from multipart / HTML messages and decoding RFC 2047
headers.

Import note: this module lives at ``job_hunt.email.reader``.  Because we use
absolute imports exclusively, ``from email import ...`` below resolves to the
Python *stdlib* ``email`` package, not to ``job_hunt.email``.  There is no
bare ``import email`` anywhere — each stdlib symbol is imported explicitly to
make the distinction clear.
"""
from __future__ import annotations

import html.parser
import imaplib
import re
import ssl
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date
from email import message_from_bytes
from email.header import decode_header as _stdlib_decode_header
from email.message import EmailMessage, Message
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from job_hunt.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Public data type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawEmail:
    """Immutable snapshot of one fetched email message."""

    mailbox: str
    uid: int
    message_id: str | None
    thread_id: str | None
    from_addr: str | None
    from_name: str | None
    subject: str | None
    received_at: str | None  # ISO-8601 UTC, e.g. "2024-01-01T12:00:00+00:00"
    body_text: str  # plain text, HTML-stripped if necessary, capped at 12 000 chars


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_THRID_RE = re.compile(rb"X-GM-THRID\s+(\d+)")

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


@contextmanager
def connect_imap(
    host: str,
    address: str,
    app_password: str,
) -> Iterator[imaplib.IMAP4_SSL]:
    """Open an authenticated IMAP4_SSL connection and yield it; logout on exit."""
    ctx = ssl.create_default_context()
    conn = imaplib.IMAP4_SSL(host, 993, ssl_context=ctx)
    conn.login(address, app_password)
    logger.info("IMAP connected: host=%s address=%s", host, address)
    try:
        yield conn
    finally:
        try:
            conn.logout()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Mailbox selection
# ---------------------------------------------------------------------------


def select_mailbox(
    conn: imaplib.IMAP4_SSL,
    mailbox: str,
) -> tuple[int, int]:
    """SELECT mailbox in read-only mode; return (uidvalidity, uidnext)."""
    conn.select(mailbox, readonly=True)
    _code, uv_data = conn.response("UIDVALIDITY")
    _code2, un_data = conn.response("UIDNEXT")
    uidvalidity = _parse_response_int(uv_data[0] if uv_data else None)
    uidnext = _parse_response_int(un_data[0] if un_data else None)
    return uidvalidity, uidnext


# ---------------------------------------------------------------------------
# Incremental fetch
# ---------------------------------------------------------------------------


def fetch_new(
    conn: imaplib.IMAP4_SSL,
    mailbox: str,
    last_uid: int,
    *,
    limit: int,
) -> list[RawEmail]:
    """Fetch emails with UID > last_uid from mailbox; return at most limit items.

    Selects the mailbox read-only before searching so the function is
    self-contained.  Uses BODY.PEEK so \\Seen is never set.

    The IMAP ``UID n:*`` range always echoes back at least the last existing
    message even when no newer messages exist; UIDs ≤ last_uid are filtered
    out before fetching.
    """
    conn.select(mailbox, readonly=True)

    _typ, search_data = conn.uid("SEARCH", None, f"UID {last_uid + 1}:*")
    if not search_data or not search_data[0]:
        return []

    raw_uids = search_data[0].split()
    # Guard: UID n:* may echo last_uid itself when no newer mail exists.
    uids = [int(u) for u in raw_uids if int(u) > last_uid]
    uids = uids[:limit]

    emails: list[RawEmail] = []
    for uid in uids:
        _typ2, fetch_data = conn.uid("FETCH", str(uid), "(BODY.PEEK[] X-GM-THRID)")
        if not fetch_data:
            continue

        raw_bytes: bytes | None = None
        header_info: bytes | None = None
        for part in fetch_data:
            if isinstance(part, tuple) and len(part) == 2:
                header_info, raw_bytes = part
                break

        if not raw_bytes:
            continue

        msg: Message = message_from_bytes(raw_bytes)

        # X-GM-THRID is in the IMAP response header, not the email headers.
        thread_id: str | None = None
        if header_info:
            m = _THRID_RE.search(header_info)
            if m:
                thread_id = m.group(1).decode()

        from_raw = msg.get("From") or ""
        from_name_raw, from_addr_raw = parseaddr(from_raw)
        from_name = _decode_header(from_name_raw) or None
        from_addr = from_addr_raw or None

        subject = _decode_header(msg.get("Subject"))
        message_id = msg.get("Message-ID")

        received_at: str | None = None
        date_val = msg.get("Date")
        if date_val:
            try:
                dt = parsedate_to_datetime(date_val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                else:
                    dt = dt.astimezone(UTC)
                received_at = dt.isoformat()
            except Exception:
                pass

        emails.append(
            RawEmail(
                mailbox=mailbox,
                uid=uid,
                message_id=message_id,
                thread_id=thread_id,
                from_addr=from_addr,
                from_name=from_name,
                subject=subject,
                received_at=received_at,
                body_text=_extract_plain_text(msg),
            )
        )

    return emails


# ---------------------------------------------------------------------------
# Plain-text extraction
# ---------------------------------------------------------------------------


def _extract_plain_text(msg: Message, *, cap: int = 12_000) -> str:
    """Return plain text from msg, preferring text/plain; HTML-stripped fallback; capped."""
    plain: str | None = None
    html_fallback: str | None = None

    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        ct = part.get_content_type()
        payload: Any = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            continue
        charset = part.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        if ct == "text/plain" and plain is None:
            plain = text
        elif ct == "text/html" and html_fallback is None:
            html_fallback = text

    if plain is not None:
        result = plain
    elif html_fallback is not None:
        result = _html_to_text(html_fallback)
    else:
        result = ""

    return result.strip()[:cap]


class _HtmlTextCollector(html.parser.HTMLParser):
    """HTMLParser subclass that collects visible text; drops script/style content."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth: int = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        """Return all collected visible text concatenated."""
        return "".join(self._parts)


def _html_to_text(html_str: str) -> str:
    """Strip HTML tags and discard script/style content; return visible text."""
    collector = _HtmlTextCollector()
    collector.feed(html_str)
    return collector.get_text()


# ---------------------------------------------------------------------------
# Header decoding
# ---------------------------------------------------------------------------


def _decode_header(value: str | None) -> str | None:
    """Decode an RFC 2047-encoded header value to a plain Unicode string."""
    if value is None:
        return None
    parts = _stdlib_decode_header(value)
    fragments: list[str] = []
    for fragment, charset in parts:
        if isinstance(fragment, bytes):
            fragments.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            fragments.append(fragment)
    result = "".join(fragments)
    return result or None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_response_int(raw: bytes | int | str | None) -> int:
    """Parse a UIDVALIDITY / UIDNEXT response value to int, returning 0 on failure."""
    if raw is None:
        return 0
    if isinstance(raw, int):
        return raw
    try:
        return int(raw.strip() if isinstance(raw, str) else raw.decode().strip())
    except (ValueError, AttributeError):
        return 0


# ---------------------------------------------------------------------------
# Reversible mailbox-mutation primitives (v2 human-confirmed actions)
# ---------------------------------------------------------------------------
# Safety contract: NO send, NO \Deleted, NO EXPUNGE, NO COPY/MOVE.
# Drafts = APPEND only (never FLAGS \Seen, never transmitted).
# Labels/archive = X-GM-LABELS +/- (reversible; Inbox label removal = archive).
# ---------------------------------------------------------------------------


def build_reply_draft(
    original: RawEmail,
    reply_body: str,
    from_address: str,
) -> bytes:
    """Build an RFC822 reply draft from *original* and return it as bytes.

    Sets To, From, Subject (Re:-prefixed unless already present), In-Reply-To,
    and References.  Does NOT send — call append_draft to save to Drafts.
    """
    msg = EmailMessage()
    msg["To"] = original.from_addr or ""
    msg["From"] = from_address
    subject = original.subject or ""
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject
    msg["Subject"] = subject
    if original.message_id:
        msg["In-Reply-To"] = original.message_id
        msg["References"] = original.message_id
    msg.set_content(reply_body)
    return msg.as_bytes()


def append_draft(
    conn: imaplib.IMAP4_SSL,
    draft_bytes: bytes,
    *,
    drafts_mailbox: str = "[Gmail]/Drafts",
) -> None:
    """Append draft_bytes to drafts_mailbox as a Draft message (never sends).

    Uses IMAP APPEND — the message is stored with the \\Draft flag and is never
    transmitted.
    """
    conn.append(
        drafts_mailbox,
        "(\\Draft)",
        imaplib.Time2Internaldate(time.time()),
        draft_bytes,
    )


_IMAP_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def has_reply_from(conn: imaplib.IMAP4_SSL, address: str, since: date) -> bool:
    """Return True if INBOX holds a message from *address* on or after *since* (read-only)."""
    if not address or any(ch in address for ch in '"\\\r\n'):
        raise ValueError("address must be a plain email address")
    # IMAP dates need English month names; strftime("%b") follows the system locale.
    imap_date = f"{since.day:02d}-{_IMAP_MONTHS[since.month - 1]}-{since.year}"
    conn.select("INBOX", readonly=True)
    _typ, data = conn.uid("SEARCH", "FROM", f'"{address}"', "SINCE", imap_date)
    return bool(data and data[0] and data[0].split())


def add_label(
    conn: imaplib.IMAP4_SSL,
    mailbox: str,
    uid: int,
    label: str,
) -> None:
    """Add a Gmail label to the message identified by *uid* (reversible; writable SELECT)."""
    conn.select(mailbox)
    conn.uid("STORE", str(uid), "+X-GM-LABELS", f"({label})")


def archive(
    conn: imaplib.IMAP4_SSL,
    mailbox: str,
    uid: int,
) -> None:
    """Remove the Inbox label from *uid* — Gmail archive (reversible; no \\Deleted or EXPUNGE)."""
    conn.select(mailbox)
    conn.uid("STORE", str(uid), "-X-GM-LABELS", "(\\Inbox)")
