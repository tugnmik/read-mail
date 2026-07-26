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
import queue
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


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _default_oauth2_target_workers() -> int:
    if os.environ.get("RENDER_EXTERNAL_URL"):
        return 2
    return 10


def _default_oauth2_min_workers() -> int:
    if os.environ.get("RENDER_EXTERNAL_URL"):
        return 1
    return 3


def _default_oauth2_stagger_seconds() -> float:
    if os.environ.get("RENDER_EXTERNAL_URL"):
        return 1.0
    return 0.6


def _default_oauth2_hard_max_workers() -> int:
    if os.environ.get("RENDER_EXTERNAL_URL"):
        return 2
    return 20


OAUTH2_HARD_MAX_WORKERS = _env_int(
    "OAUTH2_HARD_MAX_WORKERS",
    _default_oauth2_hard_max_workers(),
)
OAUTH2_TARGET_WORKERS = min(
    OAUTH2_HARD_MAX_WORKERS,
    _env_int("OAUTH2_TARGET_WORKERS", _default_oauth2_target_workers()),
)
OAUTH2_MIN_WORKERS = min(
    OAUTH2_TARGET_WORKERS,
    _env_int("OAUTH2_MIN_WORKERS", _default_oauth2_min_workers()),
)
OAUTH2_MAX_RETRIES = _env_int("OAUTH2_MAX_RETRIES", 2, minimum=0)
OAUTH2_WORKER_STAGGER_SECONDS = _env_float(
    "OAUTH2_WORKER_STAGGER_SECONDS",
    _default_oauth2_stagger_seconds(),
)


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
    access_token = body.get("access_token", "").strip()
    refresh_token = body.get("refresh_token", "").strip()
    client_id = body.get("client_id", "").strip()
    tenant_id = body.get("tenant_id", "consumers").strip() or "consumers"
    limit = body.get("limit", 10)
    email = body.get("email", "").strip()

    if not all([refresh_token, client_id]) and not access_token:
        return jsonify({"error": "Thieu refresh_token hoac client_id"}), 400

    if access_token:
        token_info = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "client_id": client_id,
            "tenant_id": tenant_id,
            "scope": body.get("scope", "").strip(),
            "api_family": "graph",
        }
    else:
        ok_token, token_or_err = exchange_refresh_token(refresh_token, client_id, tenant_id)
        if not ok_token:
            return jsonify({"error": token_or_err}), 401
        token_info = token_or_err
    ok_msgs, msgs_or_err = get_messages(token_info, limit=int(limit), email_addr=email)
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
    access_token = body.get("access_token", "").strip()
    refresh_token = body.get("refresh_token", "").strip()
    client_id = body.get("client_id", "").strip()
    tenant_id = body.get("tenant_id", "consumers").strip() or "consumers"
    message_id = body.get("message_id", "").strip()
    email = body.get("email", "").strip()

    if (not all([refresh_token, client_id]) and not access_token) or not message_id:
        return jsonify({"error": "Thieu thong tin"}), 400

    if access_token:
        token_info = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "client_id": client_id,
            "tenant_id": tenant_id,
            "scope": body.get("scope", "").strip(),
            "api_family": "graph",
        }
    else:
        ok_token, token_or_err = exchange_refresh_token(refresh_token, client_id, tenant_id)
        if not ok_token:
            return jsonify({"error": token_or_err}), 401
        token_info = token_or_err
    ok_detail, detail_or_err = get_message_detail(token_info, message_id, email_addr=email)
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


_KEEP_ALIVE_STARTED = False


def start_keep_alive():
    global _KEEP_ALIVE_STARTED
    if _KEEP_ALIVE_STARTED:
        return

    render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    if not render_url:
        return

    def _keep_alive():
        while True:
            time.sleep(600)
            try:
                _requests.get(f"{render_url}/ping", timeout=10)
            except Exception:
                pass

    _KEEP_ALIVE_STARTED = True
    threading.Thread(target=_keep_alive, daemon=True).start()


def _oauth2_result_from_token(idx, email, result, worker_id):
    payload = {
        "_idx": idx,
        "email": email,
        "attempts": result.get("attempts", 1),
        "worker_id": worker_id,
    }

    if "error" in result:
        payload.update(
            {
                "status": "error",
                "error": result.get("error", "Token failed"),
                "error_code": result.get("error_code", "unknown_error"),
            }
        )
        if "final_url" in result:
            payload["final_url"] = result["final_url"]
        return payload

    payload.update(
        {
            "status": "ok",
            "refresh_token": result["refresh_token"],
            "client_id": result["client_id"],
            "tenant_id": result.get("tenant_id", "consumers"),
            "scope": result.get("scope", ""),
        }
    )
    return payload


def _oauth2_worker(worker_id, task_queue, result_queue):
    resource_stop = False
    try:
        stagger = min(4.0, (worker_id - 1) * OAUTH2_WORKER_STAGGER_SECONDS)
        if stagger > 0:
            time.sleep(stagger)

        from playwright.sync_api import sync_playwright

        from get_hotmail_token import (
            get_token_from_credentials,
            is_resource_error,
            launch_token_browser,
        )

        with sync_playwright() as pw:
            try:
                browser = launch_token_browser(pw)
            except Exception as exc:
                result_queue.put(
                    {
                        "type": "worker_error",
                        "worker_id": worker_id,
                        "error": f"Browser launch failed: {exc}",
                    }
                )
                return

            try:
                while True:
                    try:
                        task = task_queue.get_nowait()
                    except queue.Empty:
                        break

                    idx = task["idx"]
                    email = task["email"]
                    password = task["password"]

                    if not email or not password:
                        payload = {
                            "_idx": idx,
                            "email": email,
                            "status": "error",
                            "error": "Thieu email hoac password",
                            "error_code": "missing_credentials",
                            "attempts": 0,
                            "worker_id": worker_id,
                        }
                        result_queue.put(
                            {"type": "result", "payload": payload, "resource_error": False}
                        )
                        continue

                    result = get_token_from_credentials(
                        email,
                        password,
                        max_retries=OAUTH2_MAX_RETRIES,
                        browser=browser,
                    )
                    payload = _oauth2_result_from_token(idx, email, result, worker_id)
                    resource_error = is_resource_error(result)
                    result_queue.put(
                        {
                            "type": "result",
                            "payload": payload,
                            "resource_error": resource_error,
                        }
                    )

                    if resource_error:
                        resource_stop = True
                        break
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    except ImportError:
        result_queue.put(
            {
                "type": "worker_error",
                "worker_id": worker_id,
                "error": "Playwright not installed on this server",
            }
        )
    except Exception as exc:
        result_queue.put(
            {
                "type": "worker_error",
                "worker_id": worker_id,
                "error": str(exc),
            }
        )
    finally:
        result_queue.put(
            {
                "type": "worker_done",
                "worker_id": worker_id,
                "resource_stop": resource_stop,
            }
        )


def _drain_task_queue(task_queue):
    remaining = []
    while True:
        try:
            remaining.append(task_queue.get_nowait())
        except queue.Empty:
            return remaining


def _resolve_oauth2_worker_config(total, requested_workers=None):
    if requested_workers is None:
        target_workers = OAUTH2_TARGET_WORKERS
    else:
        target_workers = max(1, min(OAUTH2_HARD_MAX_WORKERS, requested_workers))

    target_workers = max(1, min(target_workers, total))
    min_workers = min(OAUTH2_MIN_WORKERS, target_workers)
    return target_workers, max(1, min_workers)


def _stream_oauth2_batch(tasks, requested_workers=None):
    total = len(tasks)
    pending = list(tasks)
    target_workers, min_workers = _resolve_oauth2_worker_config(total, requested_workers)
    current_workers = target_workers
    emitted = 0
    ok_count = 0
    error_count = 0
    last_worker_error = ""

    while pending:
        worker_count = max(1, min(current_workers, len(pending)))
        task_queue = queue.Queue()
        result_queue = queue.Queue()

        for task in pending:
            task_queue.put(task)

        threads = []
        for worker_id in range(worker_count):
            thread = threading.Thread(
                target=_oauth2_worker,
                args=(worker_id + 1, task_queue, result_queue),
                daemon=True,
            )
            thread.start()
            threads.append(thread)

        done_workers = 0
        launch_errors = 0
        resource_errors = 0

        while done_workers < worker_count:
            message = result_queue.get()
            msg_type = message.get("type")

            if msg_type == "result":
                payload = message["payload"]
                emitted += 1
                if payload.get("status") == "ok":
                    ok_count += 1
                else:
                    error_count += 1
                if message.get("resource_error"):
                    resource_errors += 1

                payload["_progress"] = f"{emitted}/{total}"
                payload["_worker_count"] = worker_count
                payload["_target_workers"] = target_workers
                payload["_ok_count"] = ok_count
                payload["_error_count"] = error_count
                yield json.dumps(payload, ensure_ascii=False) + "\n"

            elif msg_type == "worker_error":
                launch_errors += 1
                last_worker_error = message.get("error", "OAuth2 worker error")

            elif msg_type == "worker_done":
                done_workers += 1

        for thread in threads:
            thread.join(timeout=2)

        remaining = _drain_task_queue(task_queue)
        if not remaining:
            break

        if worker_count > min_workers:
            current_workers = max(min_workers, worker_count - max(1, launch_errors + resource_errors))
            pending = remaining
            continue

        for task in remaining:
            emitted += 1
            error_count += 1
            payload = {
                "_idx": task["idx"],
                "email": task["email"],
                "status": "error",
                "error": last_worker_error or "OAuth2 worker unavailable",
                "error_code": "worker_unavailable",
                "attempts": 0,
                "_progress": f"{emitted}/{total}",
                "_worker_count": worker_count,
                "_target_workers": target_workers,
                "_ok_count": ok_count,
                "_error_count": error_count,
            }
            yield json.dumps(payload, ensure_ascii=False) + "\n"
        break


# API: Lay refresh_token tu nhieu email + password (NDJSON stream)
@app.route("/api/get-token-stream", methods=["POST"])
def api_get_token_stream():
    body = request.get_json(silent=True) or {}
    raw_accounts = body.get("accounts", [])
    requested_workers = body.get("workers")

    if not isinstance(raw_accounts, list) or not raw_accounts:
        return jsonify({"error": "Khong co account nao"}), 400

    if requested_workers is not None:
        try:
            requested_workers = int(requested_workers)
        except (TypeError, ValueError):
            return jsonify({"error": "workers phai la so nguyen"}), 400

    tasks = []
    for idx, acc in enumerate(raw_accounts):
        if not isinstance(acc, dict):
            tasks.append({"idx": idx, "email": "", "password": ""})
            continue
        tasks.append(
            {
                "idx": idx,
                "email": acc.get("email", "").strip(),
                "password": acc.get("password", "").strip(),
            }
        )

    return Response(
        _stream_oauth2_batch(tasks, requested_workers=requested_workers),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
            return jsonify({
                "error": result["error"],
                "error_code": result.get("error_code", "unknown_error"),
                "attempts": result.get("attempts", 1),
            }), 401
        return jsonify({
            "refresh_token": result["refresh_token"],
            "client_id":     result["client_id"],
            "tenant_id":     result.get("tenant_id", "consumers"),
            "scope":         result.get("scope", ""),
            "attempts":      result.get("attempts", 1),
        })
    except ImportError:
        return jsonify({"error": "Playwright not installed on this server"}), 501
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Main ────────────────────────────────────────────────────────────
start_keep_alive()


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
