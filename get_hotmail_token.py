"""
get_hotmail_token.py
====================
Lấy refresh_token cho Hotmail/Outlook.com personal accounts
từ email + password sử dụng Playwright headless browser.

Cách dùng:
  python get_hotmail_token.py email@outlook.com password123

Yêu cầu:
  pip install playwright
  playwright install chromium

Kết quả in ra:
  email|password|refresh_token|client_id
  (dùng paste vào web app)
"""
import sys, urllib.parse, requests
from playwright.sync_api import sync_playwright

CLIENT_ID    = "881fbb00-671b-4907-b21e-18c7c7aeb585"
REDIRECT_URI = "https://login.live.com/oauth20_desktop.srf"
SCOPE        = ("https://graph.microsoft.com/Mail.Read "
                "https://graph.microsoft.com/IMAP.AccessAsUser.All "
                "offline_access openid")
TOKEN_URL    = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"


def get_token_from_credentials(email: str, password: str) -> dict:
    """
    Trả về dict: {refresh_token, client_id, scope}
    Hoặc dict {error: ...} nếu thất bại.
    """
    auth_url = (
        "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?"
        + urllib.parse.urlencode({
            "client_id":     CLIENT_ID,
            "response_type": "code",
            "redirect_uri":  REDIRECT_URI,
            "scope":         SCOPE,
            "response_mode": "query",
            "prompt":        "login",
        })
    )

    auth_code = {"value": None}

    def extract_code(url: str):
        if "code=" in url:
            p = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            return p.get("code", [None])[0]
        return None

    def intercept_request(req):
        if REDIRECT_URI in req.url:
            code = extract_code(req.url)
            if code:
                auth_code["value"] = code

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_context().new_page()
        page.on("request", intercept_request)

        try:
            page.goto(auth_url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # Step 1: Fill email
            page.fill('input[type="email"], input[name="loginfmt"], input[name="login"]',
                      email, timeout=8000)
            page.click('input[type="submit"], button[type="submit"], #idSIButton9',
                       timeout=5000)
            page.wait_for_load_state("networkidle", timeout=10000)

            # Step 2: Fill password
            page.fill('input[type="password"], input[name="passwd"]',
                      password, timeout=8000)
            page.click('input[type="submit"], button[type="submit"], #idSIButton9',
                       timeout=5000)

            # Step 3: Poll loop - xử lý các trang trung gian
            for _ in range(25):
                if auth_code["value"]:
                    break

                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass

                url = page.url

                # Đã có code trong URL
                if REDIRECT_URI in url:
                    code = extract_code(url)
                    if code:
                        auth_code["value"] = code
                    break

                # Lỗi rõ ràng từ Microsoft
                if "error=" in url and REDIRECT_URI not in url:
                    break

                # KMSI "Stay signed in?" → click No
                if "KmsiInterrupt" in url or "kmsi" in url.lower():
                    try:
                        page.click('#idBtn_Back', timeout=3000)
                    except Exception:
                        try:
                            page.click('button:has-text("No")', timeout=3000)
                        except Exception:
                            pass
                    continue

                # Consent page → Accept
                if "Consent" in url or "consent" in url:
                    try:
                        page.click('button:has-text("Accept")', timeout=5000)
                    except Exception:
                        pass
                    continue

                # "Action Required" / "Protect your account" / MFA setup → skip nếu có nút
                try:
                    skip_btn = page.locator(
                        'button:has-text("Skip"), '
                        'button:has-text("Not now"), '
                        'a:has-text("Skip"), '
                        'a:has-text("Not now"), '
                        '#idBtn_Back'
                    ).first
                    if skip_btn.count() > 0:
                        skip_btn.click(timeout=3000)
                        continue
                except Exception:
                    pass

                # "Suspicious activity" confirm → click Continue
                try:
                    cont_btn = page.locator(
                        'button:has-text("Continue"), '
                        'input[value="Continue"]'
                    ).first
                    if cont_btn.count() > 0:
                        cont_btn.click(timeout=3000)
                        continue
                except Exception:
                    pass

                page.wait_for_timeout(1000)

            # Kiểm tra final URL
            if not auth_code["value"]:
                code = extract_code(page.url)
                if code:
                    auth_code["value"] = code

        except Exception as e:
            browser.close()
            return {"error": f"Browser error: {e}"}

        final_url = page.url
        browser.close()

    if not auth_code["value"]:
        # Trả về URL cuối cùng để debug
        short_url = final_url[:120] if final_url else "unknown"
        return {"error": f"No authorization code obtained. Final page: {short_url}"}

    # Exchange auth code for tokens
    resp = requests.post(TOKEN_URL, data={
        "client_id":    CLIENT_ID,
        "grant_type":   "authorization_code",
        "code":         auth_code["value"],
        "redirect_uri": REDIRECT_URI,
        "scope":        SCOPE,
    }, timeout=20)
    data = resp.json()
    if "refresh_token" not in data:
        return {"error": data.get("error_description", str(data))}

    return {
        "refresh_token": data["refresh_token"],
        "client_id":     CLIENT_ID,
        "scope":         data.get("scope", ""),
        "tenant_id":     "consumers",
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    email_arg    = sys.argv[1]
    password_arg = sys.argv[2]

    print(f"Getting token for: {email_arg} ...")
    result = get_token_from_credentials(email_arg, password_arg)

    if "error" in result:
        print(f"❌ FAILED: {result['error']}")
        sys.exit(1)

    rt = result["refresh_token"]
    cid = result["client_id"]
    print(f"✅ SUCCESS!")
    print(f"\n--- Paste vao web app (format: email|password|refresh_token|client_id) ---")
    print(f"{email_arg}|{password_arg}|{rt}|{cid}")
    print(f"\n--- Hoac chi can refresh_token + client_id ---")
    print(f"refresh_token : {rt[:60]}...")
    print(f"client_id     : {cid}")
    print(f"tenant_id     : consumers")
    print(f"scope         : {result['scope'][:80]}")
