"""
Get OAuth2 refresh tokens for Hotmail/Outlook personal accounts.

The public entrypoint is get_token_from_credentials(email, password).  It can
either launch its own browser or reuse a browser supplied by a batch worker.
Each login attempt always uses a fresh browser context.
"""

from __future__ import annotations

import sys
import time
import random
import urllib.parse
from typing import Any, Dict, Optional, Tuple

import requests
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


CLIENT_ID = "881fbb00-671b-4907-b21e-18c7c7aeb585"
REDIRECT_URI = "https://login.live.com/oauth20_desktop.srf"
SCOPE = (
    "https://graph.microsoft.com/Mail.Read "
    "https://graph.microsoft.com/IMAP.AccessAsUser.All "
    "offline_access openid"
)
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"

MAX_RETRIES = 2

RETRYABLE_ERROR_CODES = {
    "access_denied",
    "browser_timeout",
    "browser_error",
    "context_closed",
    "resource_error",
    "token_network_error",
    "token_timeout",
    "verification_required",
    "no_authorization_code",
    "consent_not_completed",
}

RESOURCE_ERROR_CODES = {
    "browser_launch_failed",
    "context_closed",
    "resource_error",
}


def build_auth_url() -> str:
    return (
        "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?"
        + urllib.parse.urlencode(
            {
                "client_id": CLIENT_ID,
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "scope": SCOPE,
                "response_mode": "query",
                "prompt": "login",
            }
        )
    )


def launch_token_browser(playwright: Any) -> Any:
    return playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    )


def extract_code(url: str) -> Optional[str]:
    if not url or "code=" not in url:
        return None
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.parse_qs(parsed.query).get("code", [None])[0]


def extract_oauth_error(url: str) -> Optional[Tuple[str, str]]:
    if not url or "error=" not in url:
        return None
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    code = qs.get("error", ["oauth_error"])[0] or "oauth_error"
    desc = qs.get("error_description", [""])[0]
    if desc:
        desc = urllib.parse.unquote_plus(desc)
    return code, desc or code


def _compact_error(message: str, max_len: int = 240) -> str:
    clean = " ".join(str(message).split())
    return clean[:max_len]


def _error(
    code: str,
    message: str,
    *,
    retryable: bool = False,
    final_url: str = "",
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "error": _compact_error(message),
        "error_code": code,
        "retryable": retryable,
    }
    if final_url:
        result["final_url"] = final_url[:180]
    return result


def _is_retryable(result: Dict[str, Any]) -> bool:
    return bool(result.get("retryable")) or result.get("error_code") in RETRYABLE_ERROR_CODES


def is_resource_error(result: Dict[str, Any]) -> bool:
    code = str(result.get("error_code", ""))
    if code in RESOURCE_ERROR_CODES:
        return True
    msg = str(result.get("error", "")).lower()
    return any(
        marker in msg
        for marker in (
            "target closed",
            "browser has been closed",
            "out of memory",
            "cannot allocate memory",
            "failed to launch",
            "executable doesn't exist",
            "executable does not exist",
        )
    )


def _new_context(browser: Any) -> Any:
    return browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        viewport={"width": 1280, "height": 900},
    )


def _click_first(page: Any, selectors: Tuple[str, ...], timeout: int = 4000) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0:
                locator.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


def _locator_label(locator: Any) -> str:
    parts = []
    for getter in (
        lambda: locator.inner_text(timeout=500),
        lambda: locator.get_attribute("value", timeout=500) or "",
        lambda: locator.get_attribute("aria-label", timeout=500) or "",
        lambda: locator.get_attribute("title", timeout=500) or "",
        lambda: locator.get_attribute("id", timeout=500) or "",
        lambda: locator.get_attribute("name", timeout=500) or "",
    ):
        try:
            value = getter()
            if value:
                parts.append(str(value))
        except Exception:
            continue
    return " ".join(parts).strip().lower()


def _click_consent_accept(page: Any) -> bool:
    explicit_selectors = (
        'button:has-text("Accept")',
        'button:has-text("Allow")',
        'button:has-text("Yes")',
        'button:has-text("Continue")',
        'button:has-text("Next")',
        'button:has-text("OK")',
        'button:has-text("I agree")',
        'input[value="Accept"]',
        'input[value="Allow"]',
        'input[value="Yes"]',
        'input[value="Continue"]',
        'input[value="Next"]',
        'input[value="OK"]',
        "#acceptButton",
        "#idSIButton9",
        'button[data-testid="appConsentPrimaryButton"]',
        "button.acceptButton",
    )
    if _click_first(page, explicit_selectors, timeout=6000):
        return True

    positive_markers = (
        "accept",
        "allow",
        "yes",
        "continue",
        "next",
        "ok",
        "agree",
        "authorize",
        "approve",
        "grant",
    )
    negative_markers = (
        "deny",
        "decline",
        "cancel",
        "no",
        "back",
        "reject",
    )

    controls = page.locator('button, input[type="submit"], input[type="button"], a[role="button"]')
    try:
        count = controls.count()
    except Exception:
        count = 0

    visible_controls = []
    for idx in range(count):
        locator = controls.nth(idx)
        try:
            if not locator.is_visible(timeout=500):
                continue
        except Exception:
            continue

        label = _locator_label(locator)
        if any(marker in label for marker in negative_markers):
            continue
        visible_controls.append(locator)
        if any(marker in label for marker in positive_markers):
            try:
                locator.click(timeout=6000)
                return True
            except Exception:
                continue

    # On account.live.com/Consent/Update the primary consent button is often
    # the rightmost/last visible button. Use this only after filtering negatives.
    for locator in reversed(visible_controls):
        try:
            locator.click(timeout=6000)
            return True
        except Exception:
            continue
    return False


def _page_text(page: Any) -> str:
    try:
        return page.content().lower()
    except Exception:
        return ""


def _has_visible_text(page: Any, texts: Tuple[str, ...]) -> bool:
    for text in texts:
        try:
            locator = page.get_by_text(text, exact=False).first
            if locator.count() > 0 and locator.is_visible(timeout=1000):
                return True
        except Exception:
            continue
    return False


def _detect_blocking_page(page: Any, url: str) -> Optional[Dict[str, Any]]:
    lower_url = (url or "").lower()

    invalid_markers = (
        "your account or password is incorrect",
        "password is incorrect",
        "incorrect password",
        "that microsoft account doesn't exist",
        "that microsoft account does not exist",
        "enter a valid email address",
    )
    if _has_visible_text(page, invalid_markers):
        return _error("invalid_credentials", "Invalid email or password")

    locked_markers = (
        "account has been locked",
        "temporarily blocked",
        "sign-in is blocked",
        "account is blocked",
    )
    if _has_visible_text(page, locked_markers):
        return _error("account_locked", "Account is locked or sign-in is blocked")

    verify_markers = (
        "verify your identity",
        "approve sign in request",
        "enter code",
        "security code",
        "two-step verification",
        "authenticator app",
    )
    if _has_visible_text(page, verify_markers) or "proofs/" in lower_url:
        return _error(
            "verification_required",
            "Account requires verification or MFA",
            retryable=True,
            final_url=url,
        )

    return None


def _handle_intermediate_page(page: Any, url: str) -> bool:
    lower_url = (url or "").lower()

    if "kmsi" in lower_url or "kmsiinterrupt" in lower_url:
        return _click_first(
            page,
            (
                "#idBtn_Back",
                'button[data-testid="no"]',
                'button:has-text("No")',
                'input[value="No"]',
            ),
        )

    if "consent" in lower_url or "permission" in lower_url:
        return _click_consent_accept(page)

    if _click_first(
        page,
        (
            'button:has-text("Skip")',
            'button:has-text("Not now")',
            'button:has-text("Skip for now")',
            'button:has-text("No thanks")',
            'button:has-text("Maybe later")',
            'button:has-text("Remind me later")',
            'a:has-text("Skip")',
            'a:has-text("Not now")',
            'a:has-text("No thanks")',
            'a:has-text("Maybe later")',
        ),
    ):
        return True

    # Continue is useful for benign Microsoft interstitials, but blocking
    # verification pages are detected before this function is called.
    return _click_first(
        page,
        (
            'button:has-text("Continue")',
            'input[value="Continue"]',
        ),
    )


def _get_auth_code_once(browser: Any, email: str, password: str) -> Dict[str, Any]:
    auth_url = build_auth_url()
    auth_code = {"value": None}
    final_url = ""
    context = None

    def capture_url(url: str) -> None:
        code = extract_code(url)
        if code:
            auth_code["value"] = code

    def intercept_request(req: Any) -> None:
        if REDIRECT_URI in req.url or "code=" in req.url:
            capture_url(req.url)

    def intercept_response(resp: Any) -> None:
        if REDIRECT_URI in resp.url or "code=" in resp.url:
            capture_url(resp.url)

    try:
        context = _new_context(browser)
        page = context.new_page()
        page.on("request", intercept_request)
        page.on("response", intercept_response)

        page.goto(auth_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(
            'input[type="email"], input[name="loginfmt"], input[name="login"]',
            timeout=30000,
        )

        page.fill(
            'input[type="email"], input[name="loginfmt"], input[name="login"]',
            email,
        )
        page.click(
            'input[type="submit"], button[type="submit"], #idSIButton9',
            timeout=8000,
        )

        try:
            page.wait_for_selector(
                'input[type="password"], input[name="passwd"]',
                timeout=20000,
            )
            page.fill('input[type="password"], input[name="passwd"]', password)
            page.click(
                'input[type="submit"], button[type="submit"], #idSIButton9',
                timeout=8000,
            )
        except PlaywrightTimeoutError:
            pass

        for _ in range(70):
            if auth_code["value"]:
                break

            try:
                page.wait_for_load_state("domcontentloaded", timeout=6000)
            except Exception:
                pass

            final_url = page.url
            capture_url(final_url)
            if auth_code["value"]:
                break

            oauth_error = extract_oauth_error(final_url)
            if oauth_error:
                code, desc = oauth_error
                return _error(code, desc, retryable=(code == "access_denied"), final_url=final_url)

            if _handle_intermediate_page(page, final_url):
                page.wait_for_timeout(1500)
                continue

            blocking = _detect_blocking_page(page, final_url)
            if blocking:
                return blocking

            try:
                password_field = page.locator('input[type="password"], input[name="passwd"]').first
                if password_field.count() > 0 and not password_field.input_value():
                    password_field.fill(password)
                    page.click(
                        'input[type="submit"], button[type="submit"], #idSIButton9',
                        timeout=5000,
                    )
                    continue
            except Exception:
                pass

            page.wait_for_timeout(1000)

        final_url = page.url
        if not auth_code["value"]:
            capture_url(final_url)

        if auth_code["value"]:
            return {"auth_code": auth_code["value"]}

        oauth_error = extract_oauth_error(final_url)
        if oauth_error:
            code, desc = oauth_error
            return _error(code, desc, retryable=(code == "access_denied"), final_url=final_url)

        lower_final_url = (final_url or "").lower()
        if "consent" in lower_final_url or "permission" in lower_final_url:
            return _error(
                "consent_not_completed",
                f"Consent page did not complete. Final page: {final_url[:120] or 'unknown'}",
                retryable=True,
                final_url=final_url,
            )

        return _error(
            "no_authorization_code",
            f"No authorization code obtained. Final page: {final_url[:120] or 'unknown'}",
            retryable=True,
            final_url=final_url,
        )
    except PlaywrightTimeoutError as exc:
        return _error("browser_timeout", f"Browser timeout: {exc}", retryable=True, final_url=final_url)
    except PlaywrightError as exc:
        msg = str(exc)
        lower = msg.lower()
        if "target closed" in lower or "browser has been closed" in lower:
            return _error("context_closed", f"Browser context closed: {msg}", retryable=True, final_url=final_url)
        if "cannot allocate memory" in lower or "out of memory" in lower:
            return _error("resource_error", f"Browser resource error: {msg}", retryable=True, final_url=final_url)
        return _error("browser_error", f"Browser error: {msg}", retryable=True, final_url=final_url)
    except Exception as exc:
        return _error("browser_error", f"Browser error: {exc}", retryable=True, final_url=final_url)
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass


def _exchange_auth_code(auth_code: str) -> Dict[str, Any]:
    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "client_id": CLIENT_ID,
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": REDIRECT_URI,
                "scope": SCOPE,
            },
            timeout=20,
        )
    except requests.Timeout as exc:
        return _error("token_timeout", f"Token exchange timeout: {exc}", retryable=True)
    except requests.RequestException as exc:
        return _error("token_network_error", f"Token exchange network error: {exc}", retryable=True)

    try:
        data = resp.json()
    except ValueError:
        return _error("token_http_error", f"Token exchange returned HTTP {resp.status_code}")

    if "refresh_token" not in data:
        code = data.get("error", "token_exchange_failed")
        desc = data.get("error_description") or str(data)
        return _error(code, desc)

    return {
        "refresh_token": data["refresh_token"],
        "client_id": CLIENT_ID,
        "scope": data.get("scope", ""),
        "tenant_id": "consumers",
    }


def _get_token_with_browser(
    browser: Any,
    email: str,
    password: str,
    *,
    max_retries: int = MAX_RETRIES,
) -> Dict[str, Any]:
    last_error: Optional[Dict[str, Any]] = None
    total_attempts = max(1, max_retries + 1)

    for attempt in range(1, total_attempts + 1):
        code_result = _get_auth_code_once(browser, email, password)
        if "auth_code" in code_result:
            token_result = _exchange_auth_code(code_result["auth_code"])
            if "error" not in token_result:
                token_result["attempts"] = attempt
                return token_result
            last_error = token_result
        else:
            last_error = code_result

        last_error["attempts"] = attempt
        if attempt >= total_attempts or not _is_retryable(last_error):
            return last_error

        time.sleep(min(1.0 + attempt * 1.5, 5.0) + random.uniform(0.2, 1.2))

    if last_error:
        return last_error
    return _error("unknown_error", "Unknown token error")


def get_token_from_credentials(
    email: str,
    password: str,
    *,
    max_retries: int = MAX_RETRIES,
    browser: Any = None,
) -> Dict[str, Any]:
    """
    Return {refresh_token, client_id, scope, tenant_id, attempts} on success.
    Return {error, error_code, attempts} on failure.
    """
    if browser is not None:
        return _get_token_with_browser(browser, email, password, max_retries=max_retries)

    try:
        with sync_playwright() as pw:
            try:
                owned_browser = launch_token_browser(pw)
            except Exception as exc:
                return _error("browser_launch_failed", f"Browser launch failed: {exc}", retryable=True)
            try:
                return _get_token_with_browser(
                    owned_browser,
                    email,
                    password,
                    max_retries=max_retries,
                )
            finally:
                try:
                    owned_browser.close()
                except Exception:
                    pass
    except Exception as exc:
        return _error("browser_error", f"Browser error: {exc}", retryable=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    email_arg = sys.argv[1]
    password_arg = sys.argv[2]

    print(f"Getting token for: {email_arg} ...")
    result = get_token_from_credentials(email_arg, password_arg)

    if "error" in result:
        print(f"FAILED: {result['error']} ({result.get('error_code', 'unknown')})")
        sys.exit(1)

    rt = result["refresh_token"]
    cid = result["client_id"]
    print("SUCCESS!")
    print("\n--- Paste into web app (format: email|password|refresh_token|client_id) ---")
    print(f"{email_arg}|{password_arg}|{rt}|{cid}")
    print("\n--- Token details ---")
    print(f"refresh_token : {rt[:60]}...")
    print(f"client_id     : {cid}")
    print("tenant_id     : consumers")
    print(f"scope         : {result.get('scope', '')[:80]}")
    print(f"attempts      : {result.get('attempts', 1)}")
