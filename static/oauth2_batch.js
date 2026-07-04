(function () {
    const DEFAULT_WORKERS = 10;

    const input = document.getElementById("oauth2-cred-input");
    const lineCount = document.getElementById("oauth2-cred-line-count");
    const statusEl = document.getElementById("oauth2-status");
    const results = document.getElementById("oauth2-results-container");

    function updateOAuth2CredLineCountBatch() {
        if (!input || !lineCount) return;
        const lines = input.value.trim().split("\n").filter((line) => line.trim());
        lineCount.textContent = `${lines.length} dong`;
    }

    function parseOAuth2Tasks(raw) {
        const tasks = [];
        const lines = raw.split("\n").map((line) => line.trim()).filter(Boolean);
        for (const line of lines) {
            const parts = line.split("|");
            if (parts.length < 2) continue;
            const email = parts[0].trim();
            const password = parts.slice(1).join("|").trim();
            if (!email || !password) continue;
            tasks.push({ email, password });
        }
        return tasks;
    }

    async function readNdjson(resp, onResult) {
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop();

            for (const line of lines) {
                const trimmed = line.trim();
                if (trimmed) onResult(JSON.parse(trimmed));
            }
        }

        if (buffer.trim()) onResult(JSON.parse(buffer.trim()));
    }

    function renderOAuth2CardBatch(idx, email) {
        const card = document.createElement("div");
        card.className = "oauth2-card";
        card.id = `oauth2-card-${idx}`;
        card.innerHTML = `
            <div class="oauth2-card-header">
                <span class="account-email">${escHtml(email)}</span>
                <span id="oauth2-badge-${idx}" style="padding:3px 10px;border-radius:12px;font-size:0.78rem;font-weight:500;background:rgba(93,122,146,0.1);color:var(--text-muted);border:1px solid var(--border-color);">Waiting</span>
            </div>
            <div class="oauth2-card-body" id="oauth2-body-${idx}">
                <span style="color:var(--text-muted);font-size:0.85rem;">Queued for OAuth2 worker...</span>
            </div>
        `;
        results.appendChild(card);
    }

    function updateOAuth2CardStatusBatch(idx, state, fullFormat, errorMsg, meta = {}) {
        const badge = document.getElementById(`oauth2-badge-${idx}`);
        const body = document.getElementById(`oauth2-body-${idx}`);
        const card = document.getElementById(`oauth2-card-${idx}`);
        if (!badge || !body || !card) return;

        const badgeBase = "padding:3px 10px;border-radius:12px;font-size:0.78rem;font-weight:500;";

        if (state === "queued") {
            badge.style.cssText = badgeBase + "background:rgba(93,122,146,0.1);color:var(--text-muted);border:1px solid var(--border-color);";
            badge.textContent = "Waiting";
            card.style.borderColor = "";
            body.innerHTML = `<span style="color:var(--text-muted);font-size:0.85rem;">Queued for OAuth2 worker...</span>`;
        } else if (state === "processing") {
            badge.style.cssText = badgeBase + "background:rgba(251,191,36,0.1);color:var(--warning);border:1px solid rgba(251,191,36,0.25);";
            badge.textContent = "Processing";
            body.innerHTML = `<span style="color:var(--text-muted);font-size:0.85rem;">Running in OAuth2 worker pool...</span>`;
        } else if (state === "ok") {
            badge.style.cssText = badgeBase + "background:var(--accent-dim);color:var(--accent);border:1px solid rgba(74,222,128,0.25);";
            badge.textContent = meta.attempts && meta.attempts > 1 ? `OK (${meta.attempts} attempts)` : "OK";
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
            badge.textContent = meta.attempts && meta.attempts > 1 ? `Error (${meta.attempts} attempts)` : "Error";
            card.style.borderColor = "rgba(248,113,113,0.3)";
            body.innerHTML = `<div style="color:var(--error);font-size:0.85rem;">${escHtml(errorMsg)}</div>`;
        }
    }

    function formatOAuth2Error(result) {
        const parts = [];
        if (result.error_code) parts.push(`[${result.error_code}]`);
        parts.push(result.error || "Token failed");
        if (result.attempts && result.attempts > 1) parts.push(`Attempts: ${result.attempts}`);
        return parts.join(" ");
    }

    async function getOAuth2Batch() {
        const raw = input.value.trim();
        if (!raw) {
            alert("Chua nhap email|password!");
            return;
        }

        const tasks = parseOAuth2Tasks(raw);
        if (tasks.length === 0) {
            alert("Format sai! Dung: email|password");
            return;
        }

        const button = document.getElementById("btn-get-oauth2");
        const cardStates = tasks.map(() => "queued");
        let doneCount = 0;
        let okCount = 0;
        let errorCount = 0;
        let workerCount = Math.min(DEFAULT_WORKERS, tasks.length);
        const startTime = performance.now();

        function markNextProcessing() {
            let activeCount = cardStates.filter((state) => state === "processing").length;
            for (let idx = 0; idx < cardStates.length && activeCount < workerCount; idx++) {
                if (cardStates[idx] === "queued") {
                    cardStates[idx] = "processing";
                    updateOAuth2CardStatusBatch(idx, "processing");
                    activeCount++;
                }
            }
        }

        function updateStatus() {
            statusEl.textContent = `Dang xu ly ${doneCount}/${tasks.length} - ${okCount} OK, ${errorCount} loi - ${workerCount} worker`;
        }

        button.disabled = true;
        results.innerHTML = "";
        Object.keys(oauth2TokenMap).forEach((key) => delete oauth2TokenMap[key]);

        tasks.forEach((task, idx) => renderOAuth2CardBatch(idx, task.email));
        markNextProcessing();
        updateStatus();

        try {
            const resp = await fetch("/api/get-token-stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ accounts: tasks }),
            });

            if (!resp.ok) {
                const errData = await resp.json();
                statusEl.textContent = `Loi: ${errData.error || resp.statusText}`;
                return;
            }

            await readNdjson(resp, (result) => {
                const idx = Number.isInteger(result._idx) ? result._idx : -1;
                if (idx < 0 || idx >= tasks.length) return;
                if (cardStates[idx] === "ok" || cardStates[idx] === "error") return;

                workerCount = result._worker_count || workerCount;
                if (result.status === "ok") {
                    okCount++;
                    cardStates[idx] = "ok";
                    const task = tasks[idx];
                    const fullFormat = `${task.email}|${task.password}|${result.refresh_token}|${result.client_id}`;
                    updateOAuth2CardStatusBatch(idx, "ok", fullFormat, null, { attempts: result.attempts || 1 });
                } else {
                    errorCount++;
                    cardStates[idx] = "error";
                    updateOAuth2CardStatusBatch(idx, "error", null, formatOAuth2Error(result), { attempts: result.attempts || 1 });
                }

                doneCount = okCount + errorCount;
                markNextProcessing();
                updateStatus();
            });

            const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
            statusEl.textContent = `Hoan thanh ${doneCount}/${tasks.length} - ${okCount} OK, ${errorCount} loi - ${elapsed}s`;
        } catch (err) {
            statusEl.textContent = `Loi ket noi: ${err.message}`;
        } finally {
            button.disabled = false;
        }
    }

    const hint = document.querySelector(".oauth2-limit-hint");
    if (hint) hint.textContent = "10 luong cung luc";
    if (input) {
        input.placeholder = "Nhap moi dong: email|password\n\nVi du:\nuser@outlook.com|password123\nuser2@hotmail.com|pass456";
        input.addEventListener("input", updateOAuth2CredLineCountBatch);
    }

    window.getOAuth2 = getOAuth2Batch;
    window.updateOAuth2CredLineCount = updateOAuth2CredLineCountBatch;
    updateOAuth2CredLineCountBatch();
})();
