"""IMAP XOAUTH2 mail reader for Hotmail/Outlook.

Fallback method for reading mail when Graph/Outlook REST APIs
don't work (e.g., MSA tokens with IMAP-only scope).
Uses stdlib imaplib — no extra dependencies.
"""

from __future__ import annotations

import email
import email.header
import email.policy
import email.utils
import imaplib
import re
from typing import Dict, List, Tuple

IMAP_HOST = "outlook.office365.com"
IMAP_PORT = 993
IMAP_TIMEOUT = 20


def _decode_header_value(raw: str) -> str:
    """Decode MIME-encoded header value (RFC 2047)."""
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded_parts: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded_parts.append(part)
    return " ".join(decoded_parts)


def _parse_from_header(from_str: str) -> Dict[str, str]:
    """Parse From header into name and address components."""
    if not from_str:
        return {"name": "", "address": ""}
    decoded = _decode_header_value(from_str)
    name, addr = email.utils.parseaddr(decoded)
    return {"name": name, "address": addr}


def _parse_date_to_iso(date_str: str) -> str:
    """Parse RFC 2822 date into ISO 8601 format."""
    if not date_str:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        return dt.isoformat()
    except Exception:
        return date_str


def _strip_html_tags(html: str) -> str:
    """Naive HTML tag removal for body preview."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def read_messages_imap(
    access_token: str, email_addr: str, limit: int = 10
) -> Tuple[bool, List[Dict] | str]:
    """Read inbox messages via IMAP XOAUTH2.

    Returns the same dict format as ``graph_api_service.get_messages``
    so callers can treat it as a drop-in fallback.
    """
    auth_string = f"user={email_addr}\x01auth=Bearer {access_token}\x01\x01"

    imap: imaplib.IMAP4_SSL | None = None
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=IMAP_TIMEOUT)
        imap.authenticate("XOAUTH2", lambda _x: auth_string.encode())
        imap.select("INBOX", readonly=True)

        status, search_data = imap.search(None, "ALL")
        if status != "OK":
            return False, "IMAP search failed"

        msg_ids = search_data[0].split()
        if not msg_ids:
            return True, []

        # Newest first, capped at *limit*
        latest_ids = list(reversed(msg_ids[-limit:]))

        messages: List[Dict] = []
        for mid in latest_ids:
            try:
                fetch_spec = (
                    "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)]"
                    " BODY.PEEK[TEXT]<0.600>)"
                )
                f_status, f_data = imap.fetch(mid, fetch_spec)
                if f_status != "OK" or not f_data:
                    continue

                header_bytes = b""
                body_bytes = b""
                for item in f_data:
                    if not isinstance(item, tuple) or len(item) != 2:
                        continue
                    desc = item[0].decode("ascii", errors="replace").upper()
                    if "HEADER" in desc:
                        header_bytes = item[1]
                    elif "TEXT" in desc or "BODY" in desc:
                        body_bytes = item[1]

                msg = email.message_from_bytes(
                    header_bytes, policy=email.policy.default
                )

                subject = (
                    _decode_header_value(str(msg.get("Subject", "")))
                    or "(no subject)"
                )
                from_info = _parse_from_header(str(msg.get("From", "")))
                date_iso = _parse_date_to_iso(str(msg.get("Date", "")))

                snippet = ""
                if body_bytes:
                    raw_body = body_bytes.decode("utf-8", errors="replace")
                    snippet = _strip_html_tags(raw_body)[:200]

                messages.append(
                    {
                        "id": f"imap_{mid.decode()}",
                        "subject": subject,
                        "from_name": from_info["name"],
                        "from_address": from_info["address"],
                        "date": date_iso,
                        "snippet": snippet,
                    }
                )
            except Exception:
                continue

        return True, messages

    except imaplib.IMAP4.error as exc:
        return False, f"IMAP auth failed: {exc}"
    except Exception as exc:
        return False, f"IMAP error: {exc}"
    finally:
        if imap:
            try:
                imap.logout()
            except Exception:
                pass


def read_message_detail_imap(
    access_token: str, email_addr: str, message_id: str
) -> Tuple[bool, Dict | str]:
    """Read full email body and detail via IMAP XOAUTH2."""
    if message_id.startswith("imap_"):
        mid = message_id[5:]
    else:
        mid = message_id

    auth_string = f"user={email_addr}\x01auth=Bearer {access_token}\x01\x01"
    imap: imaplib.IMAP4_SSL | None = None
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=IMAP_TIMEOUT)
        imap.authenticate("XOAUTH2", lambda _x: auth_string.encode())
        imap.select("INBOX", readonly=True)

        status, data = imap.fetch(mid.encode(), "(RFC822)")
        if status != "OK" or not data:
            return False, f"Failed to fetch message {message_id}"

        raw_email = b""
        for response_part in data:
            if isinstance(response_part, tuple):
                raw_email = response_part[1]
                break

        if not raw_email:
            return False, "Empty email content"

        msg = email.message_from_bytes(raw_email, policy=email.policy.default)

        subject = _decode_header_value(str(msg.get("Subject", ""))) or "(no subject)"
        from_info = _parse_from_header(str(msg.get("From", "")))
        date_iso = _parse_date_to_iso(str(msg.get("Date", "")))

        # Extract html or text body
        html_body = ""
        content_type = "html"

        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                cdispo = str(part.get("Content-Disposition", ""))

                if ctype == "text/html" and "attachment" not in cdispo:
                    html_body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                    content_type = "html"
                    break
                elif ctype == "text/plain" and "attachment" not in cdispo:
                    html_body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                    content_type = "text"
            if not html_body:
                # Fallback to any text part
                for part in msg.walk():
                    ctype = part.get_content_type()
                    if ctype in ("text/html", "text/plain"):
                        html_body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                        content_type = "html" if ctype == "text/html" else "text"
                        break
        else:
            ctype = msg.get_content_type()
            html_body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")
            content_type = "html" if ctype == "text/html" else "text"

        snippet = _strip_html_tags(html_body)[:200]

        return True, {
            "id": message_id,
            "subject": subject,
            "from_name": from_info["name"],
            "from_address": from_info["address"],
            "date": date_iso,
            "snippet": snippet,
            "html_body": html_body,
            "content_type": content_type,
        }

    except Exception as exc:
        return False, f"IMAP detail error: {exc}"
    finally:
        if imap:
            try:
                imap.logout()
            except Exception:
                pass

