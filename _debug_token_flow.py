"""
DEBUG SCRIPT: Kiem tra cac phuong phap lay refresh_token tu email+password
cho Hotmail/Outlook.com personal accounts.

Test theo thu tu:
  1. Verify token da co (full format)
  2. ROPC qua live.com (endpoint cu cua MSA)
  3. ROPC qua v1 endpoint (/common/oauth2/token, khong co /v2.0/)
  4. ROPC qua consumers v2 voi nhieu client IDs
  5. Xac nhan ket qua bang cach doc thu thuc su
"""
import requests, json, re

# ─── TAI KHOAN TEST ────────────────────────────────────────────────────────
EMAIL    = "JamesMartinhma892@outlook.com"
PASSWORD = "fn4mmTPp"
KNOWN_RT = ("M.C504_BAY.0.U.-ChlnYn*F*7YUahKUmFTDBn1lFc6CHB8tvSOosGDsSCTfs2i5KH0JC0aM"
            "Lgg17*Lt3MKl7RKzr7YPYeE6kanFag4oFGt1*1qqA9JF1CZCaTzcQC3vXkHhyMiVaXMD7dE*"
            "KejxRGXDUdn2GExBsW8gZ17oZfQHNcnrwYclYsfn*MQ*XUsK2gvmYEETMcdjVXoC8RJOedAm"
            "ZhQtw078Z0rIJxYsMX8*gWNtooouSOWgHgWKHbZNkhMHILRGljF!FA7Nok0h3hpDHU0LQ1VR"
            "YZRmDYGi8aRagnBffNNvi4Pt0ongsKDZNXCLNm6rpClJ1tYH93AMZi6j0TAmBTaSbIuHxsb9z"
            "7qH1UD!QnKl6WLBtH2pR98FwAW74yxp0IvPNRNxrhEos5MEhknLw4LdyFtmDBE$")
KNOWN_CID = "881fbb00-671b-4907-b21e-18c7c7aeb585"

SEP = "=" * 70

def print_result(label, data):
    if "refresh_token" in data:
        rt = data["refresh_token"]
        print(f"  ✅ refresh_token: {rt[:60]}...")
        print(f"  scope : {data.get('scope','')[:80]}")
        print(f"  token_type: {data.get('token_type')}, expires_in: {data.get('expires_in')}")
        return data["refresh_token"]
    else:
        err = data.get("error_description") or data.get("error") or str(data)
        print(f"  ❌ {err[:120]}")
        return None

# ═══════════════════════════════════════════════════════════════════
# BUOC 1: Verify token da co
# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("BUOC 1: Verify token da co (full format)")
print(SEP)
r = requests.post(
    "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
    data={
        "client_id":     KNOWN_CID,
        "grant_type":    "refresh_token",
        "refresh_token": KNOWN_RT,
    }, timeout=20
)
d = r.json()
step1_rt = print_result("consumers v2 + known CID", d)
if step1_rt:
    print(f"\n  client_id su dung: {KNOWN_CID}")
    print(f"  => Token da co HOAT DONG voi endpoint consumers/v2")

# ═══════════════════════════════════════════════════════════════════
# BUOC 2: ROPC qua live.com (MSA native endpoint)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("BUOC 2: ROPC qua login.live.com (MSA native)")
print(SEP)
# Cac scope MSA native (Windows Live)
live_scopes = [
    ("wl offline (basic)", "wl.imap wl.emails wl.offline_access"),
    ("MSA offline",        "https://outlook.live.com/mail.readwrite offline_access"),
]
# Cac client IDs hoat dong voi live.com
live_cids = [
    ("Windows Live ID (Xbox)",  "000000004C12AE6F"),
    ("Known CID tu full format", KNOWN_CID),
]
step2_rt = step2_cid = None
for cid_name, cid in live_cids:
    for scope_name, scope in live_scopes:
        payload = {"client_id": cid, "grant_type": "password",
                   "username": EMAIL, "password": PASSWORD, "scope": scope}
        r = requests.post("https://login.live.com/oauth20_token.srf",
                          data=payload, timeout=20)
        d = r.json()
        print(f"\n  [{cid_name} / {scope_name}]")
        rt = print_result("", d)
        if rt and not step2_rt:
            step2_rt = rt
            step2_cid = cid
            print(f"  => SUCCESS! client_id={cid}")

# ═══════════════════════════════════════════════════════════════════
# BUOC 3: ROPC qua Azure AD v1 endpoint (khong co /v2.0/)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("BUOC 3: ROPC qua v1 endpoint (/common/oauth2/token)")
print(SEP)
v1_configs = [
    ("Office EWS + resource",     "d3590ed6-52b3-4102-aeff-aad2292ab01c",
     None, "https://outlook.office365.com"),
    ("Known CID + resource",      KNOWN_CID,
     None, "https://outlook.office365.com"),
    ("Known CID + resource2",     KNOWN_CID,
     None, "https://outlook.office.com"),
]
step3_rt = step3_cid = None
for name, cid, scope, resource in v1_configs:
    payload = {"client_id": cid, "grant_type": "password",
               "username": EMAIL, "password": PASSWORD,
               "resource": resource}
    if scope:
        payload["scope"] = scope
    r = requests.post(
        "https://login.microsoftonline.com/common/oauth2/token",
        data=payload, timeout=20)
    d = r.json()
    print(f"\n  [{name}]")
    rt = print_result("", d)
    if rt and not step3_rt:
        step3_rt = rt
        step3_cid = cid

# ═══════════════════════════════════════════════════════════════════
# BUOC 4: ROPC qua v2 consumers voi nhieu client IDs
# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("BUOC 4: ROPC qua consumers/v2 voi cac client IDs")
print(SEP)
v2_configs = [
    ("Windows Mail",         "9e5f94bc-e8a4-4e73-b8be-63364c29d753",
     "https://outlook.office.com/Mail.Read offline_access"),
    ("Known CID",            KNOWN_CID,
     "https://outlook.office.com/Mail.Read offline_access"),
    ("Known CID Graph",      KNOWN_CID,
     "Mail.Read offline_access"),
    ("Known CID EWS",        KNOWN_CID,
     "https://outlook.office365.com/EWS.AccessAsUser.All offline_access"),
]
step4_rt = step4_cid = None
for name, cid, scope in v2_configs:
    r = requests.post(
        "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
        data={"client_id": cid, "grant_type": "password",
              "username": EMAIL, "password": PASSWORD, "scope": scope},
        timeout=20)
    d = r.json()
    print(f"\n  [{name}]")
    rt = print_result("", d)
    if rt and not step4_rt:
        step4_rt = rt
        step4_cid = cid

# ═══════════════════════════════════════════════════════════════════
# BUOC 5: Doc thu thuc su bang token lay duoc
# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("BUOC 5: Xac nhan doc thu bang token thanh cong nhat")
print(SEP)

from graph_api_service import exchange_refresh_token, get_messages

for label, rt, cid, tenant in [
    ("Token da co (KNOWN_RT + consumers)", KNOWN_RT, KNOWN_CID, "consumers"),
    ("ROPC live.com result", step2_rt, step2_cid, "consumers") if step2_rt else (None, None, None, None),
    ("ROPC v1 result",       step3_rt, step3_cid, "consumers") if step3_rt else (None, None, None, None),
    ("ROPC v2 result",       step4_rt, step4_cid, "consumers") if step4_rt else (None, None, None, None),
]:
    if not label or not rt:
        continue
    print(f"\n  [{label}]")
    ok, info = exchange_refresh_token(rt, cid, tenant)
    if not ok:
        print(f"  ❌ exchange: {info}")
        continue
    ok2, msgs = get_messages(info, 2)
    if ok2:
        print(f"  ✅ DOC THANH CONG (api={info.get('api_family')})")
        for m in msgs:
            print(f"     - {m.get('subject','(no subject)')}")
    else:
        print(f"  ❌ get_messages: {msgs}")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("TOM TAT:")
print(f"  Step 2 (live.com ROPC): {'✅ THANH CONG' if step2_rt else '❌ THAT BAI'}")
print(f"  Step 3 (v1 ROPC):       {'✅ THANH CONG' if step3_rt else '❌ THAT BAI'}")
print(f"  Step 4 (v2 consumers):  {'✅ THANH CONG' if step4_rt else '❌ THAT BAI'}")
print(SEP)
