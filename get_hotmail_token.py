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

    def intercept_request(req):
        if REDIRECT_URI in req.url and "code=" in req.url:
            p = urllib.parse.parse_qs(urllib.parse.urlparse(req.url).query)
            auth_code["value"] = p.get("code", [None])[0]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        page    = browser.new_context().new_page()
        page.on("request", intercept_request)

        page.goto(auth_url, timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)

        # Fill email
        page.fill('input[type="email"], input[name="loginfmt"], input[name="login"]',
                  email, timeout=8000)
        page.click('input[type="submit"], button[type="submit"], #idSIButton9',
                   timeout=5000)
        page.wait_for_load_state("networkidle", timeout=10000)

        # Fill password
        page.fill('input[type="password"], input[name="passwd"]',
                  password, timeout=8000)
        page.click('input[type="submit"], button[type="submit"], #idSIButton9',
                   timeout=5000)

        # Wait for redirect or next step
        try:
            page.wait_for_url(f"{REDIRECT_URI}*", timeout=12000)
        except Exception:
            page.wait_for_load_state("networkidle", timeout=12000)

        # Handle "Stay signed in?" (KMSI)
        if "KmsiInterrupt" in page.url:
            try:
                page.click('#idBtn_Back', timeout=4000)  # "No"
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

        # Handle consent page
        if "Consent/Update" in page.url:
            try:
                page.click('button:has-text("Accept")', timeout=5000)
                try:
                    page.wait_for_url(f"{REDIRECT_URI}*", timeout=12000)
                except Exception:
                    page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

        # Check final URL for auth code
        final_url = page.url
        if not auth_code["value"] and "code=" in final_url:
            p = urllib.parse.parse_qs(urllib.parse.urlparse(final_url).query)
            auth_code["value"] = p.get("code", [None])[0]

        browser.close()

    if not auth_code["value"]:
        return {"error": "No authorization code obtained. Check credentials or MFA."}

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
