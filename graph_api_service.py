"""Mail service layer for Hotmail/Outlook OAuth2 readers.

Some consumer refresh tokens return Outlook-scoped access tokens that work
with outlook.office.com but not Microsoft Graph. This module detects the
token family and calls the matching mail API automatically.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter, Retry

TENANT_ID = "consumers"
TOKEN_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
GRAPH_BASE = "https://graph.microsoft.com/v1.0/me"
OUTLOOK_BASE = "https://outlook.office.com/api/v2.0/me"

# Scope dùng khi exchange lại cho MSA tokens thiếu Mail.Read
GRAPH_MAIL_READ_SCOPE = "https://graph.microsoft.com/Mail.Read offline_access"
OUTLOOK_MAIL_READ_SCOPE = "https://outlook.office.com/Mail.Read offline_access"

# Keywords cho phép phát hiện token có quyền đọc mail qua REST API
_MAIL_REST_KEYWORDS = ("mail.read", "mail.readwrite", "mail.readbasic")

# Retry chỉ cho GET (mail list/detail), KHÔNG retry POST (token exchange)
_retry_strategy = Retry(
    total=1,
    backoff_factor=0.3,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET"],
)
_adapter = HTTPAdapter(
    pool_connections=50,
    pool_maxsize=100,
    max_retries=_retry_strategy,
)
_session = requests.Session()
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

# ── Token cache ───────────────────────────────────────────────────────────────
# Key: (refresh_token_stripped, client_id_stripped)
# Value: (token_info_dict, expire_at_float, canonical_refresh_token)
# Access token sống ~3600s, reuse đến khi còn 120s.
_TOKEN_CACHE_LOCK = threading.Lock()
_token_cache: Dict[str, Any] = {}   # key → (TokenInfo, expire_at)
_TOKEN_REUSE_BUFFER = 120            # giây trước khi hết hạn thì exchange lại

# ── Global circuit breaker cho token endpoint ─────────────────────────────────
# Khi gặp AADSTS50196, block mọi token exchange trong COOLDOWN giây.
_CB_LOCK = threading.Lock()
_cb_open_until: float = 0.0          # timestamp khi circuit breaker mở lại
_CB_COOLDOWN = 90                    # giây cooldown khi bị trip


def _cb_is_open() -> bool:
    """Trả True nếu circuit breaker đang mở (đang trong cooldown)."""
    with _CB_LOCK:
        return time.time() < _cb_open_until


def _cb_trip() -> None:
    """Kích hoạt cooldown toàn app khi gặp AADSTS50196."""
    with _CB_LOCK:
        global _cb_open_until
        _cb_open_until = time.time() + _CB_COOLDOWN


def _remaining_cooldown() -> int:
    with _CB_LOCK:
        remaining = _cb_open_until - time.time()
        return max(0, int(remaining))


def _cache_key(refresh_token: str, client_id: str) -> str:
    return f"{refresh_token.strip()}::{client_id.strip()}"


def _cache_get(refresh_token: str, client_id: str) -> Optional["TokenInfo"]:
    key = _cache_key(refresh_token, client_id)
    with _TOKEN_CACHE_LOCK:
        entry = _token_cache.get(key)
    if entry is None:
        return None
    token_info, expire_at = entry
    if time.time() < expire_at - _TOKEN_REUSE_BUFFER:
        return token_info
    return None


def _cache_put(old_refresh: str, client_id: str, token_info: "TokenInfo",
               expires_in: int = 3600) -> None:
    key = _cache_key(old_refresh, client_id)
    new_refresh = token_info.get("refresh_token", old_refresh)
    new_key = _cache_key(new_refresh, client_id)
    expire_at = time.time() + expires_in
    with _TOKEN_CACHE_LOCK:
        entry = (token_info, expire_at)
        _token_cache[key] = entry      # old token alias
        _token_cache[new_key] = entry  # new rotated token alias

TokenInfo = Dict[str, str]


def _has_mail_rest_scope(scope_str: str) -> bool:
    """Return True nếu scope chứa quyền đọc mail qua REST API."""
    low = scope_str.lower()
    return any(kw in low for kw in _MAIL_REST_KEYWORDS)


def _do_single_exchange(
    refresh_token: str,
    client_id: str,
    tenant_id: str = "consumers",
    scope: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Thực hiện 1 lần token exchange. Trả về (token_data, error_msg)."""
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    payload: Dict[str, str] = {
        "client_id": client_id.strip(),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token.strip(),
    }
    if scope:
        payload["scope"] = scope
    try:
        resp = _session.post(token_url, data=payload, timeout=30)
        data = resp.json()
    except Exception as exc:
        return None, f"request_error: {exc}"

    if data.get("access_token"):
        return data, ""

    err_desc = data.get("error_description", "")
    err_code = data.get("error", "")
    return None, err_desc or err_code or str(data)


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
) -> Tuple[bool, "TokenInfo | str"]:
    """Exchange refresh_token với multi-scope strategy, caching, circuit breaker.

    Strategy:
    1. Cache hit → reuse
    2. Exchange không scope (fast path cho token đã có Mail.Read)
    3. Nếu token thiếu mail scope → exchange lại với Graph Mail.Read scope
    4. Nếu thất bại → exchange lại với Outlook Mail.Read scope
    5. Nếu tất cả scope thất bại → trả token gốc (IMAP fallback)
    6. Nếu exchange không scope cũng fail → thử scoped exchange từ đầu
    """
    # 1. Kiểm tra cache trước
    cached = _cache_get(refresh_token, client_id)
    if cached is not None:
        return True, cached

    # 2. Kiểm tra circuit breaker
    if _cb_is_open():
        secs = _remaining_cooldown()
        return False, (
            f"token_error: AADSTS50196 cooldown đang hoạt động, "
            f"vui lòng chờ ~{secs}s trước khi thử lại."
        )

    # 3. Exchange không scope (nhanh, tương thích ngược)
    data, err = _do_single_exchange(refresh_token, client_id, tenant_id)

    if data:
        scope = data.get("scope", "")

        if _has_mail_rest_scope(scope):
            # Token đã có mail scope → dùng luôn (fast path)
            token_info = _build_token_info(data, refresh_token, client_id, tenant_id)
            _cache_put(refresh_token, client_id, token_info,
                       int(data.get("expires_in", 3600)))
            return True, token_info

        # Token thiếu mail scope (VD: MSA token có IMAP/POP/SMTP)
        # Thử exchange lại với scope cụ thể, dùng refresh token mới nếu bị rotate
        new_rt = data.get("refresh_token") or refresh_token
        for explicit_scope in (GRAPH_MAIL_READ_SCOPE, OUTLOOK_MAIL_READ_SCOPE):
            data_s, _ = _do_single_exchange(
                new_rt, client_id, tenant_id, scope=explicit_scope
            )
            if data_s:
                token_info = _build_token_info(
                    data_s, refresh_token, client_id, tenant_id
                )
                _cache_put(refresh_token, client_id, token_info,
                           int(data_s.get("expires_in", 3600)))
                return True, token_info

        # Không scope nào thành công → trả token gốc (IMAP fallback sẽ xử lý)
        token_info = _build_token_info(data, refresh_token, client_id, tenant_id)
        _cache_put(refresh_token, client_id, token_info,
                   int(data.get("expires_in", 3600)))
        return True, token_info

    # 4. Exchange không scope thất bại hoàn toàn
    if "50196" in err:
        _cb_trip()
        secs = _remaining_cooldown()
        return False, (
            f"token_error: AADSTS50196 - Microsoft phát hiện request loop. "
            f"Tất cả tài khoản sẽ được thử lại sau ~{secs}s."
        )

    # 5. Thử exchange với scope cụ thể (khi no-scope hoàn toàn fail)
    for explicit_scope in (GRAPH_MAIL_READ_SCOPE, OUTLOOK_MAIL_READ_SCOPE):
        data_s, _ = _do_single_exchange(
            refresh_token, client_id, tenant_id, scope=explicit_scope
        )
        if data_s:
            token_info = _build_token_info(
                data_s, refresh_token, client_id, tenant_id
            )
            _cache_put(refresh_token, client_id, token_info,
                       int(data_s.get("expires_in", 3600)))
            return True, token_info

    return False, f"token_error: {err}"


def get_messages(
    token_or_info: TokenInfo | str, limit: int = 10, email_addr: str = ""
) -> Tuple[bool, List[Dict] | str]:
    """Read messages via Graph API, Outlook REST, hoặc IMAP XOAUTH2 fallback.

    Strategy chain:
    1. Preferred REST API (Graph hoặc Outlook tùy token scope)
    2. Fallback REST API (API còn lại)
    3. IMAP XOAUTH2 (nếu có email_addr và token có IMAP scope)
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

    # Cả Graph lẫn Outlook REST đều fail → thử IMAP XOAUTH2
    if email_addr and "imap" in token_info.get("scope", "").lower():
        try:
            from imap_mail_reader import read_messages_imap

            ok, result = read_messages_imap(
                token_info["access_token"], email_addr, limit=limit
            )
            if ok:
                token_info["api_family"] = "imap"
                return True, result
        except Exception:
            pass

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
    ok_msgs, msgs_or_err = get_messages(token_info, limit=1, email_addr=email)
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
