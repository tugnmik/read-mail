"""Mail service layer for Hotmail/Outlook OAuth2 readers.

Some consumer refresh tokens return Outlook-scoped access tokens that work
with outlook.office.com but not Microsoft Graph. This module detects the
token family and calls the matching mail API automatically.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from urllib.parse import quote

import requests

TENANT_ID = "consumers"
TOKEN_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
GRAPH_BASE = "https://graph.microsoft.com/v1.0/me"
OUTLOOK_BASE = "https://outlook.office.com/api/v2.0/me"

_adapter = requests.adapters.HTTPAdapter(
    pool_connections=50,
    pool_maxsize=100,
    max_retries=1,
)
_session = requests.Session()
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

TokenInfo = Dict[str, str]


def _detect_api_family(scope: str, access_token: str) -> str:
    """Best-effort hint; get_messages / get_message_detail always try both APIs
    so a wrong guess here is corrected automatically at request time."""
    scope_value = (scope or "").lower()
    if "outlook.office.com/" in scope_value:
        return "outlook"
    # Short-name Graph scopes (e.g. "Mail.Read offline_access") have no URL prefix
    if "graph.microsoft.com/" in scope_value or "mail.read" in scope_value:
        return "graph"
    # Unknown / empty scope → default to graph (backward-compat); fallback handles rest
    return "graph"


def _build_token_info(
    token_data: Dict[str, Any], refresh_token: str, client_id: str,
    tenant_id: str = "consumers",
) -> TokenInfo:
    access_token = token_data["access_token"]
    scope = token_data.get("scope", "")
    return {
        "access_token": access_token,
        "refresh_token": token_data.get("refresh_token") or refresh_token.strip(),
        "client_id": client_id.strip(),
        "scope": scope,
        "tenant_id": tenant_id,
        "api_family": _detect_api_family(scope, access_token),
    }


def _normalize_token_info(token_or_info: TokenInfo | str) -> TokenInfo:
    if isinstance(token_or_info, dict):
        return token_or_info

    access_token = str(token_or_info).strip()
    return {
        "access_token": access_token,
        "refresh_token": "",
        "client_id": "",
        "scope": "",
        "api_family": _detect_api_family("", access_token),
    }


def _pick(data: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def _extract_from_info(message: Dict[str, Any]) -> Dict[str, str]:
    sender = _pick(message, "from", "From", default={}) or {}
    email_address = _pick(sender, "emailAddress", "EmailAddress", default={}) or {}
    return {
        "name": _pick(email_address, "name", "Name", default=""),
        "address": _pick(email_address, "address", "Address", default=""),
    }


def _format_message(message: Dict[str, Any]) -> Dict[str, str]:
    from_info = _extract_from_info(message)
    return {
        "id": _pick(message, "id", "Id", default=""),
        "subject": _pick(message, "subject", "Subject", default="(no subject)")
        or "(no subject)",
        "from_name": from_info["name"],
        "from_address": from_info["address"],
        "date": _pick(message, "receivedDateTime", "ReceivedDateTime", default=""),
        "snippet": (_pick(message, "bodyPreview", "BodyPreview", default="") or "")[:200],
    }


def _format_message_detail(message: Dict[str, Any]) -> Dict[str, str]:
    formatted = _format_message(message)
    body = _pick(message, "body", "Body", default={}) or {}
    formatted["html_body"] = _pick(body, "content", "Content", default="")
    formatted["content_type"] = _pick(body, "contentType", "ContentType", default="html")
    return formatted


def _mail_request_failed(resp: requests.Response, api_family: str) -> Tuple[bool, str]:
    detail = resp.text[:300]
    try:
        error_data = resp.json().get("error", {})
        if isinstance(error_data, dict):
            detail = error_data.get("message") or detail
        elif error_data:
            detail = str(error_data)
    except ValueError:
        pass

    api_label = "Outlook" if api_family == "outlook" else "Graph"
    if resp.status_code in (401, 403):
        return False, f"Token khong hop le hoac khong co quyen doc mail qua {api_label}: {detail}"
    return False, f"{api_label} API {resp.status_code}: {detail}"


def _messages_request_config(api_family: str, limit: int) -> Tuple[str, Dict[str, Any]]:
    if api_family == "outlook":
        return (
            f"{OUTLOOK_BASE}/messages",
            {
                "$top": limit,
                "$orderby": "ReceivedDateTime desc",
                "$select": "Id,Subject,From,ReceivedDateTime,BodyPreview",
            },
        )

    return (
        f"{GRAPH_BASE}/messages",
        {
            "$top": limit,
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,receivedDateTime,bodyPreview",
        },
    )


def _message_detail_request_config(api_family: str, message_id: str) -> Tuple[str, Dict[str, Any]]:
    quoted_message_id = quote(message_id, safe="")
    if api_family == "outlook":
        return (
            f"{OUTLOOK_BASE}/messages/{quoted_message_id}",
            {"$select": "Id,Subject,From,ReceivedDateTime,Body"},
        )

    return (
        f"{GRAPH_BASE}/messages/{quoted_message_id}",
        {"$select": "id,subject,from,receivedDateTime,body"},
    )


def exchange_refresh_token(
    refresh_token: str, client_id: str, tenant_id: str = "consumers"
) -> Tuple[bool, TokenInfo | str]:
    """Exchange refresh_token and keep token metadata for API selection.

    For personal Hotmail/Outlook.com accounts use tenant_id='consumers' (default).
    For org/school (Entra) accounts pass the tenant GUID or domain, e.g.
    tenant_id='2a141a9b-4ef4-4094-a1e5-59bf690777c6'.
    """
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    payload = {
        "client_id": client_id.strip(),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token.strip(),
    }
    try:
        resp = _session.post(token_url, data=payload, timeout=30)
        data = resp.json()
    except Exception as exc:
        return False, f"request_error: {exc}"

    access_token = data.get("access_token")
    if access_token:
        return True, _build_token_info(data, refresh_token, client_id, tenant_id)

    err = data.get("error_description") or data.get("error") or str(data)
    return False, f"token_error: {err}"


def get_messages(
    token_or_info: TokenInfo | str, limit: int = 10
) -> Tuple[bool, List[Dict] | str]:
    """Read messages, auto-detecting the right API family with a fallback retry.

    Order: preferred family first (from token scope hint), then the other one.
    The first 401/403 is silently retried on the other API; any other status
    code is returned immediately.
    """
    token_info = _normalize_token_info(token_or_info)
    headers = {
        "Authorization": f"Bearer {token_info['access_token']}",
        "Content-Type": "application/json",
    }

    preferred = token_info.get("api_family", "graph")
    fallback = "outlook" if preferred == "graph" else "graph"

    for family in (preferred, fallback):
        url, params = _messages_request_config(family, limit)
        try:
            resp = _session.get(url, headers=headers, params=params, timeout=30)
        except Exception as exc:
            return False, f"Mail API error: {exc}"

        if resp.status_code == 200:
            # Lock in the working family for subsequent detail calls
            token_info["api_family"] = family
            messages_raw = resp.json().get("value", [])
            return True, [_format_message(msg) for msg in messages_raw]

        if resp.status_code in (401, 403):
            # Permission / auth error — silently try the other API
            continue

        # Non-auth error (5xx, 400, …) — no point retrying with different API
        return _mail_request_failed(resp, family)

    return False, "Token khong co quyen doc mail (da thu ca Graph va Outlook)"


def get_message_detail(
    token_or_info: TokenInfo | str, message_id: str
) -> Tuple[bool, Dict | str]:
    """Read full email body, with the same Graph/Outlook fallback as get_messages."""
    token_info = _normalize_token_info(token_or_info)
    headers = {
        "Authorization": f"Bearer {token_info['access_token']}",
        "Content-Type": "application/json",
    }

    preferred = token_info.get("api_family", "graph")
    fallback = "outlook" if preferred == "graph" else "graph"

    for family in (preferred, fallback):
        url, params = _message_detail_request_config(family, message_id)
        try:
            resp = _session.get(url, headers=headers, params=params, timeout=30)
        except Exception as exc:
            return False, f"Mail API error: {exc}"

        if resp.status_code == 200:
            token_info["api_family"] = family
            return True, _format_message_detail(resp.json())

        if resp.status_code in (401, 403):
            continue

        return _mail_request_failed(resp, family)

    return False, "Token khong co quyen xem chi tiet mail (da thu ca Graph va Outlook)"


def process_single_account(acc: Dict) -> Dict:
    """Exchange token, pick the right mail API, and read the latest message."""
    email = acc.get("email", "").strip()
    refresh_token = acc.get("refresh_token", "").strip()
    client_id = acc.get("client_id", "").strip()
    tenant_id = acc.get("tenant_id", "consumers").strip() or "consumers"

    if not all([email, refresh_token, client_id]):
        return {"email": email, "status": "error", "error": "Thieu thong tin"}

    ok_token, token_or_err = exchange_refresh_token(refresh_token, client_id, tenant_id)
    if not ok_token:
        return {"email": email, "status": "error", "error": token_or_err}

    token_info = token_or_err
    ok_msgs, msgs_or_err = get_messages(token_info, limit=1)
    if not ok_msgs:
        return {"email": email, "status": "error", "error": msgs_or_err}

    return {
        "email": email,
        "status": "ok",
        "messages": msgs_or_err,
        "refresh_token": token_info["refresh_token"],
        "client_id": token_info["client_id"],
        "tenant_id": token_info.get("tenant_id", "consumers"),
        "mail_api": token_info["api_family"],
        "token_scope": token_info["scope"],
    }
