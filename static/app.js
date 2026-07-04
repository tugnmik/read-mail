/**
 * App logic cho web doc mail Hotmail/Outlook.
 *
 * Toi uu hieu suat:
 *  - Su dung NDJSON streaming de nhan ket qua real-time
 *  - Hien thi tung account ngay khi backend xu ly xong
 *  - Khong doi tat ca accounts moi render
 */

// ── State ──────────────────────────────────────────────────────────
const accountDataMap = {};
const oauth2TokenMap = {};
let okCount = 0;
let errCount = 0;
let totalCount = 0;

// Per-account in-flight lock: ngăn double-click spam token exchange
const _accountInFlight = {};
// Debounce: ngăn click btnRead nhiều lần liên tiếp
let _lastReadAt = 0;
const _READ_DEBOUNCE_MS = 1000;

// Chuyển lỗi kỹ thuật thành thông báo tiếng Việt thân thiện
function friendlyError(msg) {
    if (!msg) return msg;
    if (/50196|LoopDetected|cooldown|loop/i.test(msg)) {
        const match = msg.match(/(\d+)s/);
        const secs = match ? match[1] : "60";
        return `⏳ Microsoft phát hiện quá nhiều yêu cầu liên tiếp. Vui lòng chờ ~${secs}s rồi thử lại.`;
    }
    return msg;
}

// ── DOM refs ───────────────────────────────────────────────────────
const inputEl = document.getElementById("oauth2-input");
const lineCountEl = document.getElementById("line-count");
const btnClear = document.getElementById("btn-clear");
const btnRead = document.getElementById("btn-read");
const statusEl = document.getElementById("status-text");
const resultsSection = document.getElementById("results-section");
const resultsContainer = document.getElementById("results-container");
const resultsSummary = document.getElementById("results-summary");
const loadingOverlay = document.getElementById("loading-overlay");
const loadingText = document.getElementById("loading-text");
const modalOverlay = document.getElementById("modal-overlay");
const modalTitle = document.getElementById("modal-title");
const modalMeta = document.getElementById("modal-meta");
const modalIframe = document.getElementById("modal-iframe");

// ── OAuth2 DOM refs ────────────────────────────────────────────
const oauth2CredInput        = document.getElementById("oauth2-cred-input");
const oauth2CredLineCount    = document.getElementById("oauth2-cred-line-count");
const btnClearOAuth2         = document.getElementById("btn-clear-oauth2");
const oauth2StatusEl         = document.getElementById("oauth2-status");
const oauth2ResultsContainer = document.getElementById("oauth2-results-container");

// ── Events ─────────────────────────────────────────────────────────
inputEl.addEventListener("input", updateLineCount);
btnClear.addEventListener("click", () => {
    inputEl.value = "";
    updateLineCount();
});

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModalForce();
});

function updateOAuth2CredLineCount() {
    const lines = oauth2CredInput.value.trim().split("\n").filter((l) => l.trim());
    oauth2CredLineCount.textContent = `${Math.min(lines.length, 10)} dòng`;
}

oauth2CredInput.addEventListener("input", updateOAuth2CredLineCount);
btnClearOAuth2.addEventListener("click", () => {
    oauth2CredInput.value = "";
    updateOAuth2CredLineCount();
});

function updateLineCount() {
    const lines = inputEl.value.trim().split("\n").filter((l) => l.trim());
    lineCountEl.textContent = `${lines.length} dòng`;
}

// ── Parse input ────────────────────────────────────────────────────
function parseAccounts() {
    const raw = inputEl.value.trim();
    if (!raw) return [];
    const lines = raw.split("\n");
    const accounts = [];
    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        const parts = trimmed.split("|");
        if (parts.length < 4) continue;
        accounts.push({
            email: parts[0].trim(),
            password: parts[1].trim(),
            refresh_token: parts[2].trim(),
            client_id: parts[3].trim(),
            tenant_id: (parts[4] || "").trim() || "consumers",
        });
    }
    return accounts;
}

// ── Main: Đọc hòm thư (STREAMING) ─────────────────────────────────
async function readMail() {
    // Debounce: tránh spam click
    const now = Date.now();
    if (now - _lastReadAt < _READ_DEBOUNCE_MS) return;
    _lastReadAt = now;

    let accounts = parseAccounts();
    if (accounts.length === 0) {
        alert("Chưa nhập dữ liệu hoặc sai format!");
        return;
    }

    // Ưu tiên refresh_token mới nhất đã được rotate từ lần đọc trước
    accounts = accounts.map((acc) => {
        const stored = accountDataMap[acc.email];
        if (stored && stored.refresh_token) {
            return { ...acc, refresh_token: stored.refresh_token };
        }
        return acc;
    });

    // Reset state
    okCount = 0;
    errCount = 0;
    totalCount = accounts.length;

    btnRead.disabled = true;
    resultsContainer.innerHTML = "";
    resultsSection.style.display = "block";
    resultsSummary.textContent = `0/${totalCount} đang xử lý...`;
    statusEl.textContent = `Đang đọc ${totalCount} account song song...`;

    // Build a lookup map for accounts by index
    const accountsByIdx = {};
    accounts.forEach((acc, idx) => {
        accountsByIdx[idx] = acc;
    });

    const startTime = performance.now();

    try {
        const resp = await fetch("/api/read-mail-stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ accounts }),
        });

        if (!resp.ok) {
            const errData = await resp.json();
            statusEl.textContent = `Lỗi: ${errData.error || resp.statusText}`;
            btnRead.disabled = false;
            return;
        }

        // Read NDJSON stream line by line
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // Process complete lines
            const lines = buffer.split("\n");
            buffer = lines.pop(); // Keep incomplete last line in buffer

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed) continue;

                try {
                    const result = JSON.parse(trimmed);
                    const idx = result._idx;
                    const acc = accountsByIdx[idx] || {};

                    // Save to state
                    accountDataMap[result.email] = {
                        refresh_token: result.refresh_token || acc.refresh_token,
                        client_id: result.client_id || acc.client_id,
                        tenant_id: result.tenant_id || acc.tenant_id || "consumers",
                        mail_api: result.mail_api || "",
                        token_scope: result.token_scope || "",
                        messages: result.messages || [],
                    };

                    // Render immediately
                    if (result.status === "ok") {
                        okCount++;
                        renderAccountCard(result.email, result.messages || []);
                    } else {
                        errCount++;
                        renderAccountError(result.email, result.error);
                    }

                    // Update progress
                    const progress = result._progress || `${okCount + errCount}/${totalCount}`;
                    resultsSummary.textContent = `${okCount} OK · ${errCount} Lỗi · ${progress}`;
                    statusEl.textContent = `Đang xử lý: ${progress}`;
                } catch (parseErr) {
                    console.warn("NDJSON parse error:", parseErr, line);
                }
            }
        }

        // Process any remaining buffer
        if (buffer.trim()) {
            try {
                const result = JSON.parse(buffer.trim());
                const idx = result._idx;
                const acc = accountsByIdx[idx] || {};
                accountDataMap[result.email] = {
                    refresh_token: result.refresh_token || acc.refresh_token,
                    client_id: result.client_id || acc.client_id,
                    tenant_id: result.tenant_id || acc.tenant_id || "consumers",
                    mail_api: result.mail_api || "",
                    token_scope: result.token_scope || "",
                    messages: result.messages || [],
                };
                if (result.status === "ok") {
                    okCount++;
                    renderAccountCard(result.email, result.messages || []);
                } else {
                    errCount++;
                    renderAccountError(result.email, result.error);
                }
            } catch {}
        }

        const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
        resultsSummary.textContent = `${okCount} OK · ${errCount} Lỗi · Tổng ${totalCount} · ${elapsed}s`;
        statusEl.textContent = `Hoàn thành: ${okCount}/${totalCount} account trong ${elapsed}s`;
    } catch (err) {
        statusEl.textContent = `Lỗi kết nối: ${err.message}`;
    }

    btnRead.disabled = false;
}

// ── Render functions ───────────────────────────────────────────────
function renderAccountCard(email, messages) {
    const card = document.createElement("div");
    card.className = "account-card";
    card.id = `card-${sanitizeId(email)}`;
    card.style.animation = "fadeSlideIn 0.3s ease";

    card.innerHTML = `
        <div class="account-card-header">
            <span class="account-email">${escHtml(email)}</span>
            <span class="account-status ok">✓ OK</span>
        </div>
        <table class="mail-table">
            <thead>
                <tr>
                    <th class="col-stt">STT</th>
                    <th class="col-from">From</th>
                    <th class="col-time">Time</th>
                    <th class="col-content">Content</th>
                    <th class="col-action"></th>
                </tr>
            </thead>
            <tbody id="tbody-${sanitizeId(email)}">
                ${renderMailRows(messages, 0, email)}
            </tbody>
        </table>
        <div class="account-footer">
            <button class="btn-more" id="btn-more-${sanitizeId(email)}" onclick="loadMoreMails('${escAttr(email)}')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
                Xem thêm
            </button>
        </div>
    `;

    resultsContainer.appendChild(card);
}

function renderAccountError(email, error) {
    const card = document.createElement("div");
    card.className = "account-card";
    card.style.animation = "fadeSlideIn 0.3s ease";

    card.innerHTML = `
        <div class="account-card-header">
            <span class="account-email">${escHtml(email)}</span>
            <span class="account-status error">✗ Lỗi</span>
        </div>
        <div class="account-error-msg">${escHtml(error)}</div>
    `;

    resultsContainer.appendChild(card);
}

function renderMailRows(messages, startIdx, email) {
    if (!messages || messages.length === 0) {
        return `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:20px;">Không có thư</td></tr>`;
    }

    return messages
        .map((msg, i) => {
            const idx = startIdx + i + 1;
            const date = formatDate(msg.date);
            const msgId = msg.id;

            return `
            <tr>
                <td class="col-stt">${idx}</td>
                <td class="col-from">
                    <div class="from-name">${escHtml(msg.from_name || msg.from_address)}</div>
                    <div class="from-addr">${escHtml(msg.from_address)}</div>
                </td>
                <td class="col-time">${date}</td>
                <td class="col-content">
                    <div class="mail-subject">${escHtml(msg.subject)}</div>
                    <div class="mail-snippet">${escHtml(msg.snippet || "")}</div>
                </td>
                <td class="col-action">
                    <button class="btn-detail" onclick="showDetail('${escAttr(email)}', '${escAttr(msgId)}')">Chi tiết</button>
                </td>
            </tr>`;
        })
        .join("");
}

// ── Xem thêm ───────────────────────────────────────────────────────
async function loadMoreMails(email) {
    const accData = accountDataMap[email];
    if (!accData) return;

    // In-flight guard: tránh gửi nhiều request token exchange song song
    if (_accountInFlight[email]) return;
    _accountInFlight[email] = true;

    const limit = parseInt(document.getElementById("mail-limit").value) || 10;
    const btnMore = document.getElementById(`btn-more-${sanitizeId(email)}`);
    const tbody = document.getElementById(`tbody-${sanitizeId(email)}`);

    btnMore.disabled = true;
    btnMore.innerHTML = `<div class="spinner-small"></div> Đang tải...`;

    try {
        const resp = await fetch("/api/mail-all", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                refresh_token: accData.refresh_token,
                client_id: accData.client_id,
                tenant_id: accData.tenant_id || "consumers",
                limit: limit,
            }),
        });
        const data = await resp.json();

        if (data.error) {
            btnMore.textContent = friendlyError(data.error);
            btnMore.disabled = false;
            _accountInFlight[email] = false;
            return;
        }

        accData.refresh_token = data.refresh_token || accData.refresh_token;
        accData.client_id = data.client_id || accData.client_id;
        accData.tenant_id = data.tenant_id || accData.tenant_id;
        accData.mail_api = data.mail_api || accData.mail_api;
        accData.token_scope = data.token_scope || accData.token_scope;
        accData.messages = data.messages;
        tbody.innerHTML = renderMailRows(data.messages, 0, email);

        btnMore.innerHTML = `✓ Đã tải ${data.messages.length} thư`;
        btnMore.disabled = true;
        btnMore.style.color = "var(--accent)";
        btnMore.style.borderColor = "var(--accent)";
    } catch (err) {
        btnMore.textContent = `Lỗi: ${err.message}`;
        btnMore.disabled = false;
    } finally {
        _accountInFlight[email] = false;
    }
}

// ── Chi tiết (modal) ───────────────────────────────────────────────
async function showDetail(email, messageId) {
    const accData = accountDataMap[email];
    if (!accData) return;

    // In-flight guard: tránh mở modal 2 lần cùng lúc
    if (_accountInFlight[`detail_${email}_${messageId}`]) return;
    _accountInFlight[`detail_${email}_${messageId}`] = true;

    modalOverlay.classList.add("active");
    modalTitle.textContent = "Đang tải...";
    modalMeta.innerHTML = "";
    modalIframe.srcdoc = `<div style="padding:40px;text-align:center;font-family:sans-serif;color:#999;">Đang tải nội dung...</div>`;

    try {
        const resp = await fetch("/api/mail-detail", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                refresh_token: accData.refresh_token,
                client_id: accData.client_id,
                tenant_id: accData.tenant_id || "consumers",
                message_id: messageId,
            }),
        });
        const data = await resp.json();

        if (data.error) {
            modalTitle.textContent = "Lỗi";
            modalIframe.srcdoc = `<div style="padding:40px;text-align:center;font-family:sans-serif;color:red;">${escHtml(friendlyError(data.error))}</div>`;
            _accountInFlight[`detail_${email}_${messageId}`] = false;
            return;
        }

        accData.refresh_token = data.refresh_token || accData.refresh_token;
        accData.client_id = data.client_id || accData.client_id;
        accData.tenant_id = data.tenant_id || accData.tenant_id;
        accData.mail_api = data.mail_api || accData.mail_api;
        accData.token_scope = data.token_scope || accData.token_scope;

        modalTitle.textContent = data.subject || "Chi tiết Email";
        modalMeta.innerHTML = `
            <div class="meta-row"><span class="meta-label">From:</span><span class="meta-value">${escHtml(data.from_name)} &lt;${escHtml(data.from_address)}&gt;</span></div>
            <div class="meta-row"><span class="meta-label">Date:</span><span class="meta-value">${formatDate(data.date)}</span></div>
            <div class="meta-row"><span class="meta-label">Subject:</span><span class="meta-value">${escHtml(data.subject)}</span></div>
        `;

        const htmlBody = data.html_body || `<pre>${escHtml(data.snippet || "Không có nội dung")}</pre>`;
        modalIframe.srcdoc = htmlBody;
    } catch (err) {
        modalTitle.textContent = "Lỗi";
        modalIframe.srcdoc = `<div style="padding:40px;text-align:center;font-family:sans-serif;color:red;">${escHtml(err.message)}</div>`;
    } finally {
        _accountInFlight[`detail_${email}_${messageId}`] = false;
    }
}

// ── Modal controls ─────────────────────────────────────────────────
function closeModal(event) {
    if (event.target === modalOverlay) {
        closeModalForce();
    }
}

function closeModalForce() {
    modalOverlay.classList.remove("active");
    modalIframe.srcdoc = "";
}

// ── Utilities ──────────────────────────────────────────────────────
function formatDate(isoStr) {
    if (!isoStr) return "—";
    try {
        const d = new Date(isoStr);
        const pad = (n) => String(n).padStart(2, "0");
        return `${pad(d.getHours())}:${pad(d.getMinutes())} - ${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
    } catch {
        return isoStr;
    }
}

function escHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function escAttr(str) {
    if (!str) return "";
    return str.replace(/'/g, "\\'").replace(/"/g, '\\"');
}

function sanitizeId(str) {
    return str.replace(/[^a-zA-Z0-9]/g, "_");
}

// ── Page navigation ─────────────────────────────────────────────
function switchPage(page) {
    document.getElementById("mail-page").style.display   = page === "mail"   ? "" : "none";
    document.getElementById("oauth2-page").style.display = page === "oauth2" ? "" : "none";
    document.getElementById("nav-mail").classList.toggle("active",   page === "mail");
    document.getElementById("nav-oauth2").classList.toggle("active", page === "oauth2");
}

// ── Get OAuth2 ──────────────────────────────────────────────────
async function getOAuth2() {
    const raw = oauth2CredInput.value.trim();
    if (!raw) { alert("Chưa nhập email|password!"); return; }

    const lines = raw.split("\n").map((l) => l.trim()).filter((l) => l);
    const tasks = [];
    for (const line of lines) {
        const parts = line.split("|");
        if (parts.length < 2) continue;
        tasks.push({ email: parts[0].trim(), password: parts[1].trim() });
    }

    if (tasks.length === 0) { alert("Format sai! Dùng: email|password"); return; }

    const btnGetOAuth2 = document.getElementById("btn-get-oauth2");
    btnGetOAuth2.disabled = true;
    oauth2ResultsContainer.innerHTML = "";
    oauth2StatusEl.textContent = `Đang xử lý 0/${tasks.length}...`;

    tasks.forEach((t, i) => renderOAuth2Card(i, t.email));

    let doneCount = 0;
    for (let i = 0; i < tasks.length; i++) {
        const { email, password } = tasks[i];
        updateOAuth2CardStatus(i, "processing");
        oauth2StatusEl.textContent = `Đang xử lý ${i + 1}/${tasks.length}: ${email}`;
        try {
            const resp = await fetch("/api/get-token", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password }),
            });
            const data = await resp.json();
            if (data.error) {
                updateOAuth2CardStatus(i, "error", null, data.error);
            } else {
                const fullFormat = `${email}|${password}|${data.refresh_token}|${data.client_id}`;
                updateOAuth2CardStatus(i, "ok", fullFormat);
            }
        } catch (err) {
            updateOAuth2CardStatus(i, "error", null, err.message);
        }
        doneCount++;
    }

    oauth2StatusEl.textContent = `Hoàn thành ${doneCount}/${tasks.length} tài khoản`;
    btnGetOAuth2.disabled = false;
}

function renderOAuth2Card(idx, email) {
    const card = document.createElement("div");
    card.className = "oauth2-card";
    card.id = `oauth2-card-${idx}`;
    card.innerHTML = `
        <div class="oauth2-card-header">
            <span class="account-email">${escHtml(email)}</span>
            <span id="oauth2-badge-${idx}" style="padding:3px 10px;border-radius:12px;font-size:0.78rem;font-weight:500;background:rgba(93,122,146,0.1);color:var(--text-muted);border:1px solid var(--border-color);">&#8987; Đợi...</span>
        </div>
        <div class="oauth2-card-body" id="oauth2-body-${idx}">
            <span style="color:var(--text-muted);font-size:0.85rem;">Đang chờ trong hàng...</span>
        </div>
    `;
    oauth2ResultsContainer.appendChild(card);
}

function updateOAuth2CardStatus(idx, state, fullFormat, errorMsg) {
    const badge = document.getElementById(`oauth2-badge-${idx}`);
    const body  = document.getElementById(`oauth2-body-${idx}`);
    const card  = document.getElementById(`oauth2-card-${idx}`);
    const badgeBase = "padding:3px 10px;border-radius:12px;font-size:0.78rem;font-weight:500;";

    if (state === "processing") {
        badge.style.cssText = badgeBase + "background:rgba(251,191,36,0.1);color:var(--warning);border:1px solid rgba(251,191,36,0.25);";
        badge.textContent = "\u23F3 Đang xử lý...";
        body.innerHTML = `<span style="color:var(--text-muted);font-size:0.85rem;">Đang đăng nhập qua Playwright, vui lòng chờ...</span>`;
    } else if (state === "ok") {
        badge.style.cssText = badgeBase + "background:var(--accent-dim);color:var(--accent);border:1px solid rgba(74,222,128,0.25);";
        badge.textContent = "\u2713 OK";
        card.style.borderColor = "rgba(74,222,128,0.3)";
        oauth2TokenMap[idx] = fullFormat;
        body.innerHTML = `
            <div class="oauth2-output-wrap">
                <div class="oauth2-output">${escHtml(fullFormat)}</div>
                <button class="btn-copy" onclick="copyOAuth2(this, ${idx})">Copy</button>
            </div>
        `;
    } else if (state === "error") {
        badge.style.cssText = badgeBase + "background:rgba(248,113,113,0.1);color:var(--error);border:1px solid rgba(248,113,113,0.25);";
        badge.textContent = "\u2717 Lỗi";
        card.style.borderColor = "rgba(248,113,113,0.3)";
        body.innerHTML = `<div style="color:var(--error);font-size:0.85rem;">${escHtml(errorMsg)}</div>`;
    }
}

function copyOAuth2(btn, idx) {
    const value = oauth2TokenMap[idx];
    if (!value) return;
    navigator.clipboard.writeText(value).then(() => {
        btn.textContent = "\u2713 \u0110\u00e3 copy";
        btn.classList.add("copied");
        setTimeout(() => { btn.textContent = "Copy"; btn.classList.remove("copied"); }, 2000);
    }).catch(() => {
        const ta = document.createElement("textarea");
        ta.value = value;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        btn.textContent = "\u2713 Đã copy";
        setTimeout(() => { btn.textContent = "Copy"; }, 2000);
    });
}
