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

// Chuyển lỗi kỹ thuật thành thông báo thân thiện (i18n)
function friendlyError(msg) {
    if (!msg) return msg;
    if (/50196|LoopDetected|cooldown|loop/i.test(msg)) {
        const match = msg.match(/(\d+)s/);
        const secs = match ? match[1] : "60";
        return t('friendly.loop', { s: secs });
    }
    return msg;
}

// ── In-App Toast Notification ──────────────────────────────────────
function showToast(message, type = "warning", duration = 3500) {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        container.className = "toast-container";
        container.setAttribute("aria-live", "polite");
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast-item toast-${type}`;

    let iconSvg = "";
    if (type === "warning") {
        iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
    } else if (type === "error") {
        iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`;
    } else if (type === "success") {
        iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`;
    } else {
        iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`;
    }

    toast.innerHTML = `
        <div class="toast-icon">${iconSvg}</div>
        <div class="toast-message">${escHtml(message)}</div>
        <button class="toast-close" title="Close">&times;</button>
    `;

    const closeBtn = toast.querySelector(".toast-close");
    const removeToast = () => {
        if (toast.classList.contains("toast-out")) return;
        toast.classList.add("toast-out");
        setTimeout(() => toast.remove(), 250);
    };

    closeBtn.addEventListener("click", removeToast);
    container.appendChild(toast);

    if (duration > 0) {
        setTimeout(removeToast, duration);
    }
}
window.showToast = showToast;

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
    oauth2CredLineCount.textContent = t('line.count', { n: lines.length });
}

oauth2CredInput.addEventListener("input", updateOAuth2CredLineCount);
btnClearOAuth2.addEventListener("click", () => {
    oauth2CredInput.value = "";
    updateOAuth2CredLineCount();
});

function updateLineCount() {
    const lines = inputEl.value.trim().split("\n").filter((l) => l.trim());
    lineCountEl.textContent = t('line.count', { n: lines.length });
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

// ── Main: Đọc hòm thư (CONCURRENT & RESPONSIVE) ───────────────────
async function readMail() {
    // Debounce: tránh spam click
    const now = Date.now();
    if (now - _lastReadAt < _READ_DEBOUNCE_MS) return;
    _lastReadAt = now;

    let accounts = parseAccounts();
    if (accounts.length === 0) {
        showToast(t('alert.no.data'), "warning");
        return;
    }

    // Ưu tiên refresh_token, access_token mới nhất đã được lưu từ lần đọc trước
    accounts = accounts.map((acc) => {
        const stored = accountDataMap[acc.email];
        if (stored) {
            return {
                ...acc,
                refresh_token: stored.refresh_token || acc.refresh_token,
                access_token: stored.access_token || "",
                expires_at: stored.expires_at || 0,
                scope: stored.token_scope || ""
            };
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
    resultsSummary.textContent = t('summary.progress', { total: totalCount });
    statusEl.textContent = t('status.processing', { n: totalCount });

    // 1. Tạo placeholder ngay lập tức cho tất cả các account để có giao diện trực quan
    accounts.forEach((acc, idx) => {
        createPlaceholderCard(acc.email, idx);
    });

    const startTime = performance.now();

    // 2. Chạy xử lý song song cho từng account với Fast Path (siêu nhanh ~0.3s - 0.5s)
    const processPromises = accounts.map(async (acc, idx) => {
        const email = acc.email;
        const emailId = sanitizeId(email);

        try {
            // Bước 1: FAST PATH - Gọi backend trực tiếp ngay lập tức!
            updatePlaceholderStatus(emailId, "processing", t('card.reading'));
            const fastResp = await fetch("/api/read-single", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(acc),
            });

            if (fastResp.ok) {
                const fastResult = await fastResp.json();
                if (fastResult.status === "ok") {
                    okCount++;
                    accountDataMap[fastResult.email] = {
                        refresh_token: fastResult.refresh_token || acc.refresh_token,
                        client_id: fastResult.client_id || acc.client_id,
                        tenant_id: fastResult.tenant_id || acc.tenant_id || "consumers",
                        mail_api: fastResult.mail_api || "",
                        token_scope: fastResult.token_scope || "",
                        messages: fastResult.messages || [],
                        access_token: acc.access_token || "",
                        expires_at: acc.expires_at || 0,
                    };
                    replacePlaceholderWithCard(fastResult.email, fastResult.messages || []);
                    return;
                }
            }

            // Bước 2: FALLBACK PATH - Chỉ chạy khi backend gặp lỗi / bị block IP
            updatePlaceholderStatus(emailId, "processing", t('card.fallback'));
            const res = await exchangeTokenClientSideSingle(acc);
            
            let prefetched_messages = null;
            if (res.access_token) {
                const hasMailScope = res.scope && (
                    res.scope.toLowerCase().includes("mail.read") ||
                    res.scope.toLowerCase().includes("mail.readwrite")
                );
                
                if (hasMailScope) {
                    try {
                        const graphUrl = "https://graph.microsoft.com/v1.0/me/messages?$top=10&$select=id,subject,from,receivedDateTime,bodyPreview";
                        const graphResp = await fetch(graphUrl, {
                            headers: {
                                "Authorization": `Bearer ${res.access_token}`,
                                "Content-Type": "application/json"
                            }
                        });
                        if (graphResp.ok) {
                            const graphData = await graphResp.json();
                            prefetched_messages = (graphData.value || []).map(msg => {
                                const fromObj = msg.from || {};
                                const emailAddressObj = fromObj.emailAddress || {};
                                return {
                                    id: msg.id,
                                    subject: msg.subject || "(no subject)",
                                    from_name: emailAddressObj.name || "",
                                    from_address: emailAddressObj.address || "",
                                    date: msg.receivedDateTime || "",
                                    snippet: msg.bodyPreview || ""
                                };
                            });
                        }
                    } catch (e) {
                        console.error(`Browser Graph API fetch failed for ${email}:`, e);
                    }
                }
            }

            const accountPayload = {
                ...acc,
                access_token: res.access_token || "",
                refresh_token: res.refresh_token || acc.refresh_token,
                scope: res.scope || "",
                prefetched_messages: prefetched_messages
            };

            const resp = await fetch("/api/read-single", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(accountPayload),
            });

            if (!resp.ok) {
                const errData = await resp.json();
                throw new Error(errData.error || resp.statusText);
            }

            const result = await resp.json();

            accountDataMap[result.email] = {
                refresh_token: result.refresh_token || acc.refresh_token,
                client_id: result.client_id || acc.client_id,
                tenant_id: result.tenant_id || acc.tenant_id || "consumers",
                mail_api: result.mail_api || "",
                token_scope: result.token_scope || "",
                messages: result.messages || [],
                access_token: res.access_token || acc.access_token || "",
                expires_at: res.expires_at || acc.expires_at || 0,
            };

            if (result.status === "ok") {
                okCount++;
                replacePlaceholderWithCard(result.email, result.messages || []);
            } else {
                errCount++;
                replacePlaceholderWithError(result.email, result.error);
            }

        } catch (err) {
            errCount++;
            replacePlaceholderWithError(email, err.message);
        } finally {
            const processedCount = okCount + errCount;
            resultsSummary.textContent = t('summary.live', { ok: okCount, err: errCount, processed: processedCount, total: totalCount });
            statusEl.textContent = t('status.progress', { processed: processedCount, total: totalCount });
        }
    });

    // Chờ tất cả hoàn thành để cập nhật tổng kết
    await Promise.all(processPromises);

    const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
    resultsSummary.textContent = t('summary.done', { ok: okCount, err: errCount, total: totalCount, s: elapsed });
    statusEl.textContent = t('status.done', { ok: okCount, total: totalCount, s: elapsed });
    btnRead.disabled = false;
}

// ── Render functions ───────────────────────────────────────────────
function createPlaceholderCard(email, idx) {
    const card = document.createElement("div");
    card.className = "account-card";
    card.id = `card-${sanitizeId(email)}`;
    card.style.animation = "fadeSlideIn 0.3s ease";
    card.innerHTML = `
        <div class="account-card-header">
            <span class="account-email">${escHtml(email)}</span>
            <span class="account-status waiting" id="status-badge-${sanitizeId(email)}" style="padding:3px 10px; border-radius:12px; font-size:0.78rem; font-weight:500; background:rgba(93,122,146,0.1); color:var(--text-muted); border:1px solid var(--border-color);">
                ${t('card.waiting')}
            </span>
        </div>
        <div class="account-placeholder-body" id="body-${sanitizeId(email)}" style="padding:24px; text-align:center; color:var(--text-muted); font-size:0.85rem; font-family:sans-serif;">
            <div class="spinner-small" style="display:inline-block; margin-right:8px; vertical-align:middle;"></div>
            ${t('card.queued')}
        </div>
    `;
    resultsContainer.appendChild(card);
}

function updatePlaceholderStatus(emailId, state, text) {
    const badge = document.getElementById(`status-badge-${emailId}`);
    const body = document.getElementById(`body-${emailId}`);
    if (!badge || !body) return;

    const badgeBase = "padding:3px 10px; border-radius:12px; font-size:0.78rem; font-weight:500;";

    if (state === "processing") {
        badge.style.cssText = badgeBase + "background:rgba(251,191,36,0.1); color:var(--warning); border:1px solid rgba(251,191,36,0.25);";
        badge.textContent = t('card.processing.badge');
        body.innerHTML = `
            <div class="spinner-small" style="display:inline-block; margin-right:8px; vertical-align:middle;"></div>
            ${escHtml(text)}
        `;
    }
}

function replacePlaceholderWithCard(email, messages) {
    const card = document.getElementById(`card-${sanitizeId(email)}`);
    if (!card) return;

    card.innerHTML = `
        <div class="account-card-header">
            <span class="account-email">${escHtml(email)}</span>
            <span class="account-status ok" data-i18n="card.ok">${t('card.ok')}</span>
        </div>
        <table class="mail-table">
            <thead>
                <tr>
                    <th class="col-stt" data-i18n="th.stt">${t('th.stt')}</th>
                    <th class="col-from" data-i18n="th.from">${t('th.from')}</th>
                    <th class="col-time" data-i18n="th.time">${t('th.time')}</th>
                    <th class="col-content" data-i18n="th.content">${t('th.content')}</th>
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
                <span data-i18n="card.viewmore">${t('card.viewmore')}</span>
            </button>
        </div>
    `;
}

function replacePlaceholderWithError(email, error) {
    const card = document.getElementById(`card-${sanitizeId(email)}`);
    if (!card) return;

    card.innerHTML = `
        <div class="account-card-header">
            <span class="account-email">${escHtml(email)}</span>
            <span class="account-status error" data-i18n="card.error">${t('card.error')}</span>
        </div>
        <div class="account-error-msg">${escHtml(error)}</div>
    `;
}

function renderMailRows(messages, startIdx, email) {
    if (!messages || messages.length === 0) {
        return `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:20px;" data-i18n="card.no.mail">${t('card.no.mail')}</td></tr>`;
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
                    <button class="btn-detail" data-i18n="btn.detail" onclick="showDetail('${escAttr(email)}', '${escAttr(msgId)}')">${t('btn.detail')}</button>
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

    if (btnMore) {
        btnMore.disabled = true;
        btnMore.innerHTML = `<div class="spinner-small" style="display:inline-block; margin-right:8px; vertical-align:middle;"></div> ${t('card.loading')}`;
    }

    try {
        // FAST PATH: Trực tiếp qua backend (siêu nhanh ~0.2s)
        const resp = await fetch("/api/mail-all", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                access_token: accData.access_token || "",
                refresh_token: accData.refresh_token,
                client_id: accData.client_id,
                tenant_id: accData.tenant_id || "consumers",
                limit: limit,
                email: email,
            }),
        });
        const data = await resp.json();

        if (!data.error) {
            accData.refresh_token = data.refresh_token || accData.refresh_token;
            accData.messages = data.messages;
            if (tbody) {
                tbody.innerHTML = renderMailRows(data.messages, 0, email);
            }

            if (btnMore) {
                btnMore.innerHTML = t('card.loaded', { n: data.messages.length });
                btnMore.disabled = true;
                btnMore.style.color = "var(--accent)";
                btnMore.style.borderColor = "var(--accent)";
            }
            _accountInFlight[email] = false;
            return;
        }
    } catch (err) {
        console.warn("Backend loadMore error, trying fallback:", err);
    }

    // FALLBACK PATH: Client-side Graph API
    if (accData.mail_api === "graph" || accData.mail_api === "graph_client") {
        try {
            const exchangeResult = await exchangeTokenClientSideSingle(accData);
            if (exchangeResult.access_token) {
                const graphUrl = `https://graph.microsoft.com/v1.0/me/messages?$top=${limit}&$select=id,subject,from,receivedDateTime,bodyPreview`;
                const graphResp = await fetch(graphUrl, {
                    headers: {
                        "Authorization": `Bearer ${exchangeResult.access_token}`,
                        "Content-Type": "application/json"
                    }
                });
                if (graphResp.ok) {
                    const graphData = await graphResp.json();
                    const messages = (graphData.value || []).map(msg => {
                        const fromObj = msg.from || {};
                        const emailAddressObj = fromObj.emailAddress || {};
                        return {
                            id: msg.id,
                            subject: msg.subject || "(no subject)",
                            from_name: emailAddressObj.name || "",
                            from_address: emailAddressObj.address || "",
                            date: msg.receivedDateTime || "",
                            snippet: msg.bodyPreview || ""
                        };
                    });
                    
                    accData.refresh_token = exchangeResult.refresh_token;
                    accData.messages = messages;
                    if (tbody) {
                        tbody.innerHTML = renderMailRows(messages, 0, email);
                    }

                    if (btnMore) {
                        btnMore.innerHTML = t('card.loaded', { n: messages.length });
                        btnMore.disabled = true;
                        btnMore.style.color = "var(--accent)";
                        btnMore.style.borderColor = "var(--accent)";
                    }
                    _accountInFlight[email] = false;
                    return;
                }
            }
        } catch (e) {
            console.error("Browser Graph loadMore fetch failed:", e);
        }
    }

    if (btnMore) {
        btnMore.textContent = t('card.load.error');
        btnMore.disabled = false;
    }
    _accountInFlight[email] = false;
}

// ── Chi tiết (modal) ───────────────────────────────────────────────
async function showDetail(email, messageId) {
    const accData = accountDataMap[email];
    if (!accData) return;

    // In-flight guard: tránh mở modal 2 lần cùng lúc
    if (_accountInFlight[`detail_${email}_${messageId}`]) return;
    _accountInFlight[`detail_${email}_${messageId}`] = true;

    modalOverlay.classList.add("active");
    modalTitle.textContent = t('modal.loading');
    modalMeta.innerHTML = "";
    try {
        // FAST PATH: Gọi API backend trực tiếp (siêu nhanh ~0.1s - 0.2s)
        const resp = await fetch("/api/mail-detail", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                access_token: accData.access_token || "",
                refresh_token: accData.refresh_token,
                client_id: accData.client_id,
                tenant_id: accData.tenant_id || "consumers",
                message_id: messageId,
                email: email,
            }),
        });
        const data = await resp.json();

        if (!data.error) {
            accData.refresh_token = data.refresh_token || accData.refresh_token;
            modalTitle.textContent = data.subject || t('modal.title.default');
            modalMeta.innerHTML = `
                <div class="meta-row"><span class="meta-label">From:</span><span class="meta-value">${escHtml(data.from_name)} &lt;${escHtml(data.from_address)}&gt;</span></div>
                <div class="meta-row"><span class="meta-label">Date:</span><span class="meta-value">${formatDate(data.date)}</span></div>
                <div class="meta-row"><span class="meta-label">Subject:</span><span class="meta-value">${escHtml(data.subject)}</span></div>
            `;
            const htmlBody = data.html_body || `<pre>${escHtml(data.snippet || t('modal.no.content'))}</pre>`;
            modalIframe.srcdoc = htmlBody;
            _accountInFlight[`detail_${email}_${messageId}`] = false;
            return;
        }
    } catch (e) {
        console.warn("Backend detail fetch error, trying client fallback:", e);
    }

    // FALLBACK PATH: Nếu backend fail
    if (accData.mail_api === "graph" || accData.mail_api === "graph_client") {
        try {
            const exchangeResult = await exchangeTokenClientSideSingle(accData);
            if (exchangeResult.access_token) {
                const graphUrl = `https://graph.microsoft.com/v1.0/me/messages/${messageId}`;
                const graphResp = await fetch(graphUrl, {
                    headers: {
                        "Authorization": `Bearer ${exchangeResult.access_token}`,
                        "Content-Type": "application/json"
                    }
                });
                if (graphResp.ok) {
                    const msg = await graphResp.json();
                    const fromObj = msg.from || {};
                    const emailAddressObj = fromObj.emailAddress || {};
                    const bodyObj = msg.body || {};
                    
                    modalTitle.textContent = msg.subject || t('modal.title.default');
                    modalMeta.innerHTML = `
                        <div class="meta-row"><span class="meta-label">From:</span><span class="meta-value">${escHtml(emailAddressObj.name || "")} &lt;${escHtml(emailAddressObj.address || "")}&gt;</span></div>
                        <div class="meta-row"><span class="meta-label">Date:</span><span class="meta-value">${formatDate(msg.receivedDateTime || "")}</span></div>
                        <div class="meta-row"><span class="meta-label">Subject:</span><span class="meta-value">${escHtml(msg.subject || "(no subject)")}</span></div>
                    `;
                    modalIframe.srcdoc = bodyObj.content || `<pre>${escHtml(msg.bodyPreview || "")}</pre>`;
                    accData.refresh_token = exchangeResult.refresh_token;
                    _accountInFlight[`detail_${email}_${messageId}`] = false;
                    return;
                }
            }
        } catch (e) {
            console.error("Browser Graph detail fetch failed:", e);
        }
    }

    modalTitle.textContent = t('modal.error');
    modalIframe.srcdoc = `<div style="padding:40px;text-align:center;font-family:sans-serif;color:red;">${t('modal.error')}</div>`;
    _accountInFlight[`detail_${email}_${messageId}`] = false;
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
window._supportsOAuth2Get = true;

document.addEventListener("DOMContentLoaded", async () => {
    try {
        const resp = await fetch("/api/config");
        if (resp.ok) {
            const cfg = await resp.json();
            window._supportsOAuth2Get = cfg.supports_oauth2_get;
            if (cfg.supports_oauth2_get === false) {
                const navOAuth2 = document.getElementById("nav-oauth2");
                if (navOAuth2) {
                    navOAuth2.style.display = "none";
                }
            }
        }
    } catch (e) {}
});

function switchPage(page) {
    if (page === "oauth2" && window._supportsOAuth2Get === false) {
        showToast(t('alert.oauth2.unavail'), "info");
        return;
    }
    document.getElementById("mail-page").style.display   = page === "mail"   ? "" : "none";
    document.getElementById("oauth2-page").style.display = page === "oauth2" ? "" : "none";
    document.getElementById("verify-page").style.display = page === "verify" ? "" : "none";
    document.getElementById("nav-mail").classList.toggle("active",   page === "mail");
    document.getElementById("nav-oauth2").classList.toggle("active", page === "oauth2");
    const navVerify = document.getElementById("nav-verify");
    if (navVerify) navVerify.classList.toggle("active", page === "verify");
}

// ── Get OAuth2 ──────────────────────────────────────────────────
async function getOAuth2() {
    const raw = oauth2CredInput.value.trim();
    if (!raw) { showToast(t('alert.oauth2.empty'), "warning"); return; }

    const lines = raw.split("\n").map((l) => l.trim()).filter((l) => l);
    const tasks = [];
    for (const line of lines) {
        const parts = line.split("|");
        if (parts.length < 2) continue;
        tasks.push({ email: parts[0].trim(), password: parts[1].trim() });
    }

    if (tasks.length === 0) { showToast(t('alert.oauth2.format'), "warning"); return; }

    const btnGetOAuth2 = document.getElementById("btn-get-oauth2");
    btnGetOAuth2.disabled = true;
    oauth2ResultsContainer.innerHTML = "";
    oauth2StatusEl.textContent = t('oauth2.status.processing', { i: 0, n: tasks.length, email: '' });

    tasks.forEach((t, i) => renderOAuth2Card(i, t.email));

    let doneCount = 0;
    for (let i = 0; i < tasks.length; i++) {
        const { email, password } = tasks[i];
        updateOAuth2CardStatus(i, "processing");
        oauth2StatusEl.textContent = t('oauth2.status.processing', { i: i + 1, n: tasks.length, email });
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

    oauth2StatusEl.textContent = t('oauth2.status.done', { done: doneCount, n: tasks.length });
    btnGetOAuth2.disabled = false;
}

function renderOAuth2Card(idx, email) {
    const card = document.createElement("div");
    card.className = "oauth2-card";
    card.id = `oauth2-card-${idx}`;
    card.innerHTML = `
        <div class="oauth2-card-header">
            <span class="account-email">${escHtml(email)}</span>
            <span id="oauth2-badge-${idx}" style="padding:3px 10px;border-radius:12px;font-size:0.78rem;font-weight:500;background:rgba(93,122,146,0.1);color:var(--text-muted);border:1px solid var(--border-color);">${t('oauth2.card.waiting')}</span>
        </div>
        <div class="oauth2-card-body" id="oauth2-body-${idx}">
            <span style="color:var(--text-muted);font-size:0.85rem;">${t('oauth2.card.queued')}</span>
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
        badge.textContent = t('oauth2.card.processing');
        body.innerHTML = `<span style="color:var(--text-muted);font-size:0.85rem;">${t('oauth2.card.login.wait')}</span>`;
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
        btn.textContent = t('btn.copied');
        btn.classList.add("copied");
        setTimeout(() => { btn.textContent = t('btn.copy'); btn.classList.remove("copied"); }, 2000);
    }).catch(() => {
        const ta = document.createElement("textarea");
        ta.value = value;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        btn.textContent = t('btn.copied');
        setTimeout(() => { btn.textContent = t('btn.copy'); }, 2000);
    });
}

async function exchangeTokenClientSideSingle(acc) {
    // 1. Kiểm tra cache client-side trước (nếu còn hạn > 2 phút)
    if (acc.access_token && acc.expires_at && (Date.now() < acc.expires_at - 120000)) {
        return {
            access_token: acc.access_token,
            refresh_token: acc.refresh_token,
            scope: acc.scope || "",
            expires_at: acc.expires_at
        };
    }

    try {
        const url = `https://login.microsoftonline.com/${acc.tenant_id || "consumers"}/oauth2/v2.0/token`;
        let payload = new URLSearchParams({
            client_id: acc.client_id,
            grant_type: "refresh_token",
            refresh_token: acc.refresh_token,
        });

        let resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: payload.toString()
        });
        let data = await resp.json();

        if (data.access_token) {
            const expires_at = Date.now() + (data.expires_in || 3600) * 1000;
            // Lưu vào global state nếu có
            const stored = accountDataMap[acc.email];
            if (stored) {
                stored.access_token = data.access_token;
                stored.expires_at = expires_at;
                stored.refresh_token = data.refresh_token || acc.refresh_token;
                stored.token_scope = data.scope || "";
            }
            return {
                access_token: data.access_token,
                refresh_token: data.refresh_token || acc.refresh_token,
                scope: data.scope || "",
                expires_at: expires_at
            };
        }

        // Try scoped if default exchange lacks access
        payload.set("scope", "https://graph.microsoft.com/Mail.Read offline_access");
        resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: payload.toString()
        });
        data = await resp.json();
        if (data.access_token) {
            const expires_at = Date.now() + (data.expires_in || 3600) * 1000;
            const stored = accountDataMap[acc.email];
            if (stored) {
                stored.access_token = data.access_token;
                stored.expires_at = expires_at;
                stored.refresh_token = data.refresh_token || acc.refresh_token;
                stored.token_scope = data.scope || "";
            }
            return {
                access_token: data.access_token,
                refresh_token: data.refresh_token || acc.refresh_token,
                scope: data.scope || "",
                expires_at: expires_at
            };
        }
    } catch (e) {
        console.error("exchangeTokenClientSideSingle error:", e);
    }
    return { access_token: "", refresh_token: acc.refresh_token, scope: "" };
}

// ── Verify Page ──────────────────────────────────────────────────
async function extractVerifyCode() {
    const raw = document.getElementById("verify-input").value.trim();
    if (!raw) {
        showToast(t('alert.verify.empty'), "warning");
        return;
    }
    
    // Parse like parseAccounts
    const lines = raw.split("\n");
    let account = null;
    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        const parts = trimmed.split("|");
        if (parts.length < 4) continue;
        account = {
            email: parts[0].trim(),
            password: parts[1].trim(),
            refresh_token: parts[2].trim(),
            client_id: parts[3].trim(),
            tenant_id: (parts[4] || "").trim() || "consumers",
        };
        break; // Take only the first account
    }
    
    if (!account) {
        showToast(t('alert.no.data'), "warning");
        return;
    }
    
    const sender = document.getElementById("verify-sender").value.trim();
    const limit = parseInt(document.getElementById("verify-limit").value) || 5;
    
    const container = document.getElementById("verify-results-container");
    const resultsDiv = document.getElementById("verify-results");
    
    resultsDiv.style.display = "block";
    container.innerHTML = `<div style="text-align:center;padding:20px;color:var(--text-muted);"><div class="spinner-small" style="display:inline-block; margin-right:8px; vertical-align:middle;"></div>${t('verify.searching')}</div>`;
    
    try {
        const payload = {
            ...account,
            sender_filter: sender,
            limit: limit
        };
        
        const resp = await fetch("/api/get-verification-code", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        
        const data = await resp.json();
        if (data.error) {
            throw new Error(data.error);
        }
        
        if (!data.codes || data.codes.length === 0) {
            container.innerHTML = `<div style="text-align:center;padding:20px;color:var(--text-muted);">${t('verify.notfound')}</div>`;
            return;
        }
        
        container.innerHTML = data.codes.map((item) => `
            <div class="verify-code-item">
                <div class="verify-code-display">
                    ${escHtml(item.code)}
                    <button class="verify-code-copy" onclick="copyToClipboard('${escAttr(item.code)}')">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                    </button>
                </div>
                <div class="verify-code-meta">
                    <div><strong>${t('verify.from')}:</strong> ${escHtml(item.sender)}</div>
                    <div><strong>${t('verify.subject')}:</strong> ${escHtml(item.subject)}</div>
                    <div><strong>${t('verify.time')}:</strong> ${formatDate(item.received_at || item.time || item.date)}</div>
                    ${item.type ? `<div><strong>${t('verify.type')}:</strong> ${escHtml(item.type)}</div>` : ''}
                </div>
            </div>
        `).join("");
        
    } catch (err) {
        showToast(err.message, "error");
        container.innerHTML = `<div style="text-align:center;padding:20px;color:var(--error);">${escHtml(err.message)}</div>`;
    }
}

async function extractAllCodes() {
    const raw = document.getElementById("verify-input").value.trim();
    if (!raw) {
        showToast(t('alert.verify.empty'), "warning");
        return;
    }
    
    // Similar to parseAccounts
    const lines = raw.split("\n");
    let account = null;
    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        const parts = trimmed.split("|");
        if (parts.length < 4) continue;
        account = {
            email: parts[0].trim(),
            password: parts[1].trim(),
            refresh_token: parts[2].trim(),
            client_id: parts[3].trim(),
            tenant_id: (parts[4] || "").trim() || "consumers",
        };
        break; // Take only the first account
    }
    
    if (!account) {
        showToast(t('alert.no.data'), "warning");
        return;
    }
    
    const limit = parseInt(document.getElementById("verify-limit").value) || 5;
    
    const container = document.getElementById("verify-results-container");
    const resultsDiv = document.getElementById("verify-results");
    
    resultsDiv.style.display = "block";
    container.innerHTML = `<div style="text-align:center;padding:20px;color:var(--text-muted);"><div class="spinner-small" style="display:inline-block; margin-right:8px; vertical-align:middle;"></div>${t('verify.searching')}</div>`;
    
    try {
        const payload = {
            ...account,
            limit: limit
        };
        
        const resp = await fetch("/api/latest-codes", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        
        const data = await resp.json();
        if (data.error) {
            throw new Error(data.error);
        }
        
        if (!data.codes || data.codes.length === 0) {
            container.innerHTML = `<div style="text-align:center;padding:20px;color:var(--text-muted);">${t('verify.notfound')}</div>`;
            return;
        }
        
        container.innerHTML = data.codes.map((item) => `
            <div class="verify-code-item">
                <div class="verify-code-display">
                    ${escHtml(item.code)}
                    <button class="verify-code-copy" onclick="copyToClipboard('${escAttr(item.code)}')">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                    </button>
                </div>
                <div class="verify-code-meta">
                    <div><strong>${t('verify.from')}:</strong> ${escHtml(item.sender)}</div>
                    <div><strong>${t('verify.subject')}:</strong> ${escHtml(item.subject)}</div>
                    <div><strong>${t('verify.time')}:</strong> ${formatDate(item.received_at || item.time || item.date)}</div>
                    ${item.type ? `<div><strong>${t('verify.type')}:</strong> ${escHtml(item.type)}</div>` : ''}
                </div>
            </div>
        `).join("");
        
    } catch (err) {
        showToast(err.message, "error");
        container.innerHTML = `<div style="text-align:center;padding:20px;color:var(--error);">${escHtml(err.message)}</div>`;
    }
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast(t('verify.copied') || 'Code copied!', "success");
    }).catch(() => {
        showToast("Copy failed", "error");
    });
}
