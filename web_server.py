"""
Flask web server phuc vu giao dien doc mail Hotmail/Outlook.

Toi uu hieu suat:
- ThreadPoolExecutor xu ly song song nhieu accounts
- NDJSON streaming tra ket qua real-time tung account
- Connection pooling qua requests.Session
"""

from __future__ import annotations

import json
import os
import threading
import time
import requests as _requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

from graph_api_service import (
    exchange_refresh_token,
    get_messages,
    get_message_detail,
    process_single_account,
)

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

# ── Config ──────────────────────────────────────────────────────────
# So worker toi da cho xu ly song song.
# 30 workers = 30 accounts xu ly dong thoi.
# Microsoft Graph API cho phep ~10,000 req/10min nen 30 la an toan.
MAX_WORKERS = 30


# ── Serve frontend ──────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api-docs")
def docs():
    return send_from_directory("static", "api-docs.html")


# ── API: Doc mail song song + stream ket qua (NDJSON) ──────────────
@app.route("/api/read-mail-stream", methods=["POST"])
def api_read_mail_stream():
    """Xu ly nhieu accounts SONG SONG, stream ket qua ve frontend
    theo dinh dang Newline-Delimited JSON (NDJSON).

    Moi dong la 1 JSON object cho 1 account.
    Frontend doc tung dong ngay khi nhan duoc, khong doi tat ca.
    """
    body = request.get_json(silent=True) or {}
    accounts = body.get("accounts", [])

    if not accounts:
        return jsonify({"error": "Khong co account nao"}), 400

    def generate():
        total = len(accounts)
        workers = min(MAX_WORKERS, total)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit tat ca accounts cung luc de xu ly song song
            futures = [
                executor.submit(process_single_account, acc)
                for acc in accounts
            ]

            # Yield ket qua THEO DUNG THU TU NHAP, khong theo thu tu hoan thanh
            for idx, future in enumerate(futures):
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "email": accounts[idx].get("email", ""),
                        "status": "error",
                        "error": str(exc),
                    }

                result["_idx"] = idx
                result["_progress"] = f"{idx + 1}/{total}"

                yield json.dumps(result, ensure_ascii=False) + "\n"

    return Response(
        generate(),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── API: Doc mail (sync fallback, giu tuong thich) ─────────────────
@app.route("/api/read-mail", methods=["POST"])
def api_read_mail():
    """Fallback sync: xu ly song song nhung tra ve 1 lan."""
    body = request.get_json(silent=True) or {}
    accounts = body.get("accounts", [])

    if not accounts:
        return jsonify({"error": "Khong co account nao"}), 400

    results = [None] * len(accounts)
    workers = min(MAX_WORKERS, len(accounts))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {
            executor.submit(process_single_account, acc): idx
            for idx, acc in enumerate(accounts)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                results[idx] = {
                    "email": accounts[idx].get("email", ""),
                    "status": "error",
                    "error": str(exc),
                }

    return jsonify({"results": results})


# ── API: Lay tat ca mail cua 1 account (co limit) ─────────────────
@app.route("/api/mail-all", methods=["POST"])
def api_mail_all():
    """Lay danh sach mail cua 1 account voi limit tuy chinh."""
    body = request.get_json(silent=True) or {}
    refresh_token = body.get("refresh_token", "").strip()
    client_id = body.get("client_id", "").strip()
    tenant_id = body.get("tenant_id", "consumers").strip() or "consumers"
    limit = body.get("limit", 10)

    if not all([refresh_token, client_id]):
        return jsonify({"error": "Thieu refresh_token hoac client_id"}), 400

    ok_token, token_or_err = exchange_refresh_token(refresh_token, client_id, tenant_id)
    if not ok_token:
        return jsonify({"error": token_or_err}), 401

    token_info = token_or_err
    ok_msgs, msgs_or_err = get_messages(token_info, limit=int(limit))
    if not ok_msgs:
        return jsonify({"error": msgs_or_err}), 500

    return jsonify(
        {
            "messages": msgs_or_err,
            "refresh_token": token_info["refresh_token"],
            "client_id": token_info["client_id"],
            "tenant_id": token_info.get("tenant_id", "consumers"),
            "mail_api": token_info["api_family"],
            "token_scope": token_info["scope"],
        }
    )


# ── API: Lay chi tiet 1 mail (full HTML body) ─────────────────────
@app.route("/api/mail-detail", methods=["POST"])
def api_mail_detail():
    """Lay full HTML body cua 1 message cu the."""
    body = request.get_json(silent=True) or {}
    refresh_token = body.get("refresh_token", "").strip()
    client_id = body.get("client_id", "").strip()
    tenant_id = body.get("tenant_id", "consumers").strip() or "consumers"
    message_id = body.get("message_id", "").strip()

    if not all([refresh_token, client_id, message_id]):
        return jsonify({"error": "Thieu thong tin"}), 400

    ok_token, token_or_err = exchange_refresh_token(refresh_token, client_id, tenant_id)
    if not ok_token:
        return jsonify({"error": token_or_err}), 401

    token_info = token_or_err
    ok_detail, detail_or_err = get_message_detail(token_info, message_id)
    if not ok_detail:
        return jsonify({"error": detail_or_err}), 500

    detail_or_err["refresh_token"] = token_info["refresh_token"]
    detail_or_err["client_id"] = token_info["client_id"]
    detail_or_err["tenant_id"] = token_info.get("tenant_id", "consumers")
    detail_or_err["mail_api"] = token_info["api_family"]
    detail_or_err["token_scope"] = token_info["scope"]
    return jsonify(detail_or_err)



# ── API: Ping (keep-alive cho Render free tier) ─────────────────────
@app.route("/ping", methods=["GET"])
def api_ping():
    return jsonify({"status": "ok"}), 200


# ── API: Lay refresh_token tu email + password (Playwright) ─────────
@app.route("/api/get-token", methods=["POST"])
def api_get_token():
    """
    Lay refresh_token cho Hotmail/Outlook.com personal tu email + password.
    Yeu cau Playwright duoc cai tren server.
    """
    body = request.get_json(silent=True) or {}
    email    = body.get("email", "").strip()
    password = body.get("password", "").strip()
    if not email or not password:
        return jsonify({"error": "Thieu email hoac password"}), 400

    try:
        from get_hotmail_token import get_token_from_credentials
        result = get_token_from_credentials(email, password)
        if "error" in result:
            return jsonify({"error": result["error"]}), 401
        return jsonify({
            "refresh_token": result["refresh_token"],
            "client_id":     result["client_id"],
            "tenant_id":     result.get("tenant_id", "consumers"),
            "scope":         result.get("scope", ""),
        })
    except ImportError:
        return jsonify({"error": "Playwright not installed on this server"}), 501
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Main ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Server dang chay tai http://localhost:{port}")
    print(f"Max workers: {MAX_WORKERS} (xu ly song song)")

    # Keep-alive: tu dong ping de chong sleep tren Render free tier
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    if render_url:
        def _keep_alive():
            while True:
                time.sleep(600)  # ping moi 10 phut
                try:
                    _requests.get(f"{render_url}/ping", timeout=10)
                except Exception:
                    pass
        threading.Thread(target=_keep_alive, daemon=True).start()
        print(f"Keep-alive bat dau → {render_url}/ping moi 10 phut")

    app.run(host="0.0.0.0", port=port, debug=False)
