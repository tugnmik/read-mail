"""
BUOC 7 (v2): Fix PPFT extraction tu $Config JSON + test Playwright + msal ROPC.
"""
import requests, re, json, urllib.parse, sys

EMAIL     = "JamesMartinhma892@outlook.com"
PASSWORD  = "fn4mmTPp"
CLIENT_ID = "881fbb00-671b-4907-b21e-18c7c7aeb585"
REDIRECT  = "https://login.live.com/oauth20_desktop.srf"
SCOPE     = ("https://graph.microsoft.com/Mail.Read "
             "https://graph.microsoft.com/IMAP.AccessAsUser.All "
             "offline_access openid")
SEP = "=" * 65

# ─────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("APPROACH A: requests + PPFT extraction tu $Config JSON")
print(SEP)

session = requests.Session()
session.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
})

auth_url = ("https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?"
            + urllib.parse.urlencode({
                "client_id": CLIENT_ID,
                "response_type": "code",
                "redirect_uri": REDIRECT,
                "scope": SCOPE,
                "response_mode": "query",
                "prompt": "login",
            }))
r1 = session.get(auth_url, allow_redirects=True, timeout=20)
html = r1.text
print(f"Final URL : {r1.url[:90]}")
print(f"Status    : {r1.status_code}")
print(f"Cookies   : {list(session.cookies.keys())}")

def parse_config(html_text):
    """Extract $Config JSON from page."""
    for pat in [
        r'\$Config\s*=\s*(\{.*?\});?\s*\n',
        r'var\s+ServerData\s*=\s*(\{.*?\});',
        r'\$Config\s*=\s*(\{[^;]+\});',
    ]:
        m = re.search(pat, html_text, re.DOTALL)
        if m:
            try: return json.loads(m.group(1))
            except: pass
    return {}

config1 = parse_config(html)
print(f"$Config keys ({len(config1)}): {list(config1.keys())[:12]}")
url_post1 = config1.get("urlPost") or ""
if not url_post1:
    m = re.search(r'"urlPost"\s*:\s*"([^"]+)"', html)
    url_post1 = m.group(1) if m else ""
print(f"urlPost (step1): {url_post1[:80]}")

# ── STEP 1: Submit email only (username step) ───────────────────
print("\n--- STEP 1: Submit email to get password page ---")
step1_post = {
    "login":       EMAIL,
    "loginfmt":    EMAIL,
    "type":        "11",
    "LoginOptions": "3",
    "lrt":         "",
    "lrtPartition": "",
    "hisRegion":   "",
    "hisScaleUnit": "",
    "ps":          "2",
    "i13":         "0",
    "i17":         "0",
    "i19":         "35948",
    "PPFT":        config1.get("sFT", ""),
    "canary":      config1.get("canary", ""),
    "ctx":         config1.get("sCtx", ""),
    "hpgrequestid": config1.get("sessionId", ""),
}
session.headers.update({
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://login.live.com",
    "Referer": r1.url,
})
post1_url = url_post1 or "https://login.live.com/ppsecure/post.srf"
r_step1 = session.post(post1_url, data=step1_post, allow_redirects=True, timeout=30)
html2 = r_step1.text
print(f"Step1 status: {r_step1.status_code}, url: {r_step1.url[:80]}")
print(f"Cookies after step1: {list(session.cookies.keys())}")

# ── Parse password page for PPFT ────────────────────────────────
config2  = parse_config(html2)
print(f"$Config2 keys ({len(config2)}): {list(config2.keys())[:12]}")

# sFT is the PPFT token
ppft = config2.get("sFT")
if not ppft:
    m = re.search(r'"sFT"\s*:\s*"([^"]+)"', html2)
    ppft = m.group(1) if m else None
url_post = config2.get("urlPost")
if not url_post:
    m = re.search(r'"urlPost"\s*:\s*"([^"]+)"', html2)
    url_post = m.group(1) if m else None

print(f"PPFT (sFT): {(ppft or 'NOT FOUND')[:50]}")
print(f"urlPost   : {(url_post or 'NOT FOUND')[:80]}")

# Check if already on password step or still on username
if not ppft and "passwd" not in html2 and "jsDisabled" not in html2:
    print("[hint] Page may still be username step or error page")
    print(f"HTML2 snippet: {html2[:400]}")

if ppft and url_post:
    post_data = {
        "login":        EMAIL,
        "loginfmt":     EMAIL,
        "passwd":       PASSWORD,
        "PPFT":         ppft,
        "type":         "11",
        "LoginOptions": "3",
        "ps":           "2",
        "i13":          "0",
        "i17":          "0",
        "i19":          "50387",
        "ctx":          config2.get("sCtx", ""),
        "canary":       config2.get("canary", ""),
        "hpgrequestid": config2.get("sessionId", ""),
    }
    session.headers.update({
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://login.live.com",
        "Referer": r_step1.url,
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "navigate",
    })
    r2 = session.post(url_post, data=post_data, allow_redirects=False, timeout=30)
    print(f"POST {r2.status_code}: {r2.headers.get('Location','no-location')[:80]}")

    auth_code = None
    resp = r2
    for hop in range(15):
        loc = resp.headers.get("Location", "")
        if not loc:
            body = resp.text
            mr = re.search(r'content="0;\s*url=([^"]+)"', body, re.IGNORECASE)
            if mr:
                loc = mr.group(1).replace("&amp;", "&")
            elif "jsDisabled" in body or "jsDisabled" in (resp.url or ""):
                print(f"  [hop {hop}] ❌ jsDisabled - Microsoft requires JS execution")
                break
            elif "code=" in body:
                cm = re.search(r'code=([\w\-\.]+)', body)
                if cm: auth_code = cm.group(1); print(f"✅ code in body"); break
            else:
                print(f"  [hop {hop}] END url={resp.url[:70]}")
                em = re.search(r'"error[^"]*":\s*"([^"]+)"', body)
                if em: print(f"  error: {em.group(1)}")
                break
        print(f"  hop {hop}: {loc[:80]}")
        if "code=" in loc:
            p = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
            auth_code = p.get("code", [None])[0]
            if auth_code: print(f"✅ code from redirect"); break
        if "error=" in loc:
            p = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
            print(f"❌ {p.get('error')} {p.get('error_description',[''])}"); break
        if loc.startswith("/"):
            b = urllib.parse.urlparse(resp.url); loc = f"{b.scheme}://{b.netloc}{loc}"
        resp = session.get(loc, allow_redirects=False, timeout=20)

    if auth_code:
        t = requests.post(
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
            data={"client_id": CLIENT_ID, "grant_type": "authorization_code",
                  "code": auth_code, "redirect_uri": REDIRECT, "scope": SCOPE},
            timeout=20).json()
        if "refresh_token" in t:
            print(f"\n{'✅'*3} THANH CONG! refresh_token={t['refresh_token'][:50]}...")
            print(f"scope: {t.get('scope','')[:80]}")
        else:
            print(f"❌ token exchange: {t.get('error_description','')[:120]}")
else:
    print(f"\n⚠ PPFT={bool(ppft)} urlPost={bool(url_post)} — can't continue")

# ─────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("APPROACH B: Playwright headless browser (REAL JS EXECUTION)")
print(SEP)
try:
    from playwright.sync_api import sync_playwright
    print("✅ Playwright sync_api available")

    REDIRECT_DESKTOP = "https://login.live.com/oauth20_desktop.srf"

    def run_playwright_login(email, password, client_id, scope):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context()
            page = ctx.new_page()

            # Capture redirect to detect auth code
            auth_code = {"value": None}
            def on_request(req):
                url = req.url
                if REDIRECT_DESKTOP in url and "code=" in url:
                    from urllib.parse import urlparse, parse_qs
                    p = parse_qs(urlparse(url).query)
                    auth_code["value"] = p.get("code", [None])[0]
                    print(f"  ✅ Code intercepted: {auth_code['value'][:30] if auth_code['value'] else None}...")

            page.on("request", on_request)

            # Also handle network navigation to desktop redirect
            def on_response(resp):
                url = resp.url
                if REDIRECT_DESKTOP in url:
                    if "code=" in url and not auth_code["value"]:
                        from urllib.parse import urlparse, parse_qs
                        p = parse_qs(urlparse(url).query)
                        auth_code["value"] = p.get("code", [None])[0]
                        print(f"  ✅ Code from response: {auth_code['value'][:30] if auth_code['value'] else None}...")

            page.on("response", on_response)

            auth_url_pl = ("https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?"
                        + urllib.parse.urlencode({
                            "client_id": client_id,
                            "response_type": "code",
                            "redirect_uri": REDIRECT_DESKTOP,
                            "scope": scope,
                            "response_mode": "query",
                            "prompt": "login",
                        }))
            print(f"  Navigate: {auth_url_pl[:70]}...")
            page.goto(auth_url_pl, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            print(f"  Page URL: {page.url[:80]}")

            # Fill email
            try:
                page.fill('input[type="email"], input[name="loginfmt"], input[name="login"]',
                          email, timeout=8000)
                print(f"  Filled email: {email}")
            except Exception as e:
                print(f"  [warn] email fill: {e}")

            # Click Next / submit
            try:
                page.click('input[type="submit"], button[type="submit"], #idSIButton9',
                           timeout=5000)
                print("  Clicked Next")
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception as e:
                print(f"  [warn] click Next: {e}")

            print(f"  Page URL after email: {page.url[:80]}")

            # Fill password
            try:
                page.fill('input[type="password"], input[name="passwd"]',
                          password, timeout=8000)
                print("  Filled password")
            except Exception as e:
                print(f"  [warn] password fill: {e}")

            # Click Sign In
            try:
                page.click('input[type="submit"], button[type="submit"], #idSIButton9',
                           timeout=5000)
                print("  Clicked Sign In")
                # Wait for redirect or next page
                try:
                    page.wait_for_url(f"{REDIRECT_DESKTOP}*", timeout=15000)
                except:
                    page.wait_for_load_state("networkidle", timeout=15000)
            except Exception as e:
                print(f"  [warn] click signin: {e}")

            final_url = page.url
            print(f"  Final URL: {final_url[:100]}")

            # Check final URL for code
            if not auth_code["value"] and "code=" in final_url:
                from urllib.parse import urlparse, parse_qs
                p = parse_qs(urlparse(final_url).query)
                auth_code["value"] = p.get("code", [None])[0]

            # Handle "Stay signed in?" page
            if not auth_code["value"] and "KmsiInterrupt" in final_url:
                print("  'Stay signed in?' page detected, clicking No")
                try:
                    page.click('#idBtn_Back, button[data-testid="no"]', timeout=5000)
                    try:
                        page.wait_for_url(f"{REDIRECT_DESKTOP}*", timeout=10000)
                    except:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    final_url = page.url
                    print(f"  Final URL after KMSI: {final_url[:100]}")
                    if "code=" in final_url:
                        from urllib.parse import urlparse, parse_qs
                        p = parse_qs(urlparse(final_url).query)
                        auth_code["value"] = p.get("code", [None])[0]
                except Exception as e:
                    print(f"  [warn] KMSI click: {e}")

            # Handle consent page at account.live.com/Consent/Update
            if not auth_code["value"] and "Consent/Update" in final_url:
                print(f"  Consent/Update page - clicking Accept...")
                try:
                    # Two buttons: Deny (left, gray) and Accept (right, blue)
                    # Must click Accept specifically by text
                    for sel in [
                        'button:has-text("Accept")',
                        'input[value="Accept"]',
                        '#acceptButton',
                        'button.acceptButton',
                        'button:last-of-type',           # Accept is the last/rightmost button
                        'button >> text=Accept',
                    ]:
                        try:
                            page.click(sel, timeout=4000)
                            print(f"  Clicked: {sel}")
                            try:
                                page.wait_for_url(f"{REDIRECT_DESKTOP}*", timeout=12000)
                            except:
                                page.wait_for_load_state("networkidle", timeout=12000)
                            final_url = page.url
                            print(f"  URL after consent: {final_url[:100]}")
                            if "code=" in final_url:
                                from urllib.parse import urlparse, parse_qs
                                p = parse_qs(urlparse(final_url).query)
                                auth_code["value"] = p.get("code", [None])[0]
                            break
                        except Exception as ex:
                            print(f"  sel '{sel}' failed: {ex.__class__.__name__}")
                            continue
                except Exception as e:
                    print(f"  [warn] consent handling: {e}")

            browser.close()
            return auth_code["value"]

    code = run_playwright_login(EMAIL, PASSWORD, CLIENT_ID, SCOPE)
    if code:
        print(f"\n✅ Got auth code: {code[:40]}...")
        tr = requests.post(
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
            data={"client_id": CLIENT_ID, "grant_type": "authorization_code",
                  "code": code, "redirect_uri": REDIRECT, "scope": SCOPE},
            timeout=20).json()
        if "refresh_token" in tr:
            rt = tr["refresh_token"]
            print(f"\n{'='*65}")
            print(f"✅✅✅ PLAYWRIGHT THANH CONG!")
            print(f"refresh_token = {rt[:60]}...")
            print(f"scope         = {tr.get('scope','')[:80]}")
            print(f"Dung client_id: {CLIENT_ID}")
            print(f"Endpoint: consumers/v2, redirect: {REDIRECT}")
            print(f"{'='*65}")
            # Save for verification
            with open("_last_token.txt", "w") as f:
                f.write(rt)
            # Verify: read mail with new token
            print("\n--- Verify: doc thu voi token moi ---")
            try:
                import sys; sys.path.insert(0, ".")
                from graph_api_service import exchange_refresh_token, get_messages
                info2 = exchange_refresh_token(rt, CLIENT_ID, "consumers")
                if "error" in str(info2):
                    print(f"Exchange err: {info2}")
                else:
                    msgs = get_messages(info2["access_token"], info2.get("api_family","graph"))
                    if isinstance(msgs, list):
                        print(f"✅ Doc duoc {len(msgs)} thu:")
                        for m3 in msgs[:3]:
                            print(f"  - {(m3.get('subject') or '(no subject)')[:60]}")
                    else:
                        print(f"get_messages: {msgs}")
            except Exception as ex:
                print(f"Verify error: {ex}")
        else:
            print(f"❌ Token exchange: {tr.get('error_description','?')[:120]}")
    else:
        print("❌ Playwright: no auth code obtained")

except ImportError:
    print("❌ Playwright not installed. pip install playwright && playwright install chromium")

# ─────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("APPROACH C: msal PublicClientApplication")
print(SEP)
try:
    import msal
    print(f"✅ msal {msal.__version__}")
    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority="https://login.microsoftonline.com/consumers",
    )
    result = app.acquire_token_by_username_password(
        EMAIL, PASSWORD,
        scopes=["https://graph.microsoft.com/Mail.Read", "offline_access"]
    )
    if "refresh_token" in result:
        print(f"✅ MSAL OK! rt={result['refresh_token'][:40]}...")
    else:
        print(f"❌ MSAL: {(result.get('error_description') or result.get('error','?'))[:120]}")
except ImportError:
    print("❌ msal not installed")
except Exception as e:
    print(f"❌ msal error: {e}")

# ─────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("APPROACH D: Device Code Flow (khi user co mat)")
print(SEP)
try:
    import msal
    app2 = msal.PublicClientApplication(
        CLIENT_ID,
        authority="https://login.microsoftonline.com/consumers",
    )
    flow = app2.initiate_device_flow(
        scopes=["https://graph.microsoft.com/Mail.Read", "offline_access"]
    )
    if "user_code" in flow:
        print(f"✅ Device Code flow kha dung:")
        print(f"   URL  : {flow['verification_uri']}")
        print(f"   Code : {flow['user_code']}")
        print(f"   (Day la cach interactive, user phai nhap code vao browser)")
    else:
        print(f"❌ {flow}")
except Exception as e:
    print(f"❌ device flow: {e}")

