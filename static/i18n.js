/**
 * i18n.js — Lightweight bilingual (VI/EN) system for read-mail web app.
 * Usage:
 *   t('key')           → returns translated string for current lang
 *   setLang('en')      → switch language and re-render all [data-i18n] elements
 */

// ── Translation dictionary ────────────────────────────────────────────────────
const TRANSLATIONS = {
    vi: {
        // Header / Nav
        'nav.readmail':    'Đọc Mail',
        'nav.getoauth2':   'Get OAuth2',
        'nav.apidocs':     'Tài Liệu API',
        'nav.gitstar':     'Give me a star',
        'logo.title':      'Đọc Hòm Thư',

        // Mail page — section header
        'mail.section.title':   'Nhập tài khoản',
        'mail.section.hint':    '(Graph API / OAuth2)',
        'mail.limit.label':     'Số thư tối đa:',
        'mail.textarea.placeholder':
            'Nhập mỗi dòng: email|password|refresh_token|client_id\n\nVí dụ:\nuser@hotmail.com|password123|M.C524_BAY.0.U.-xxxxx|9e5f94bc-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
        'mail.clear':           'Xóa',
        'mail.btn.read':        'Đọc hòm thư',
        'mail.results.title':   'Kết quả',

        // OAuth2 page
        'oauth2.section.title': 'Get OAuth2 Token',
        'oauth2.workers.label': 'Workers:',
        'oauth2.workers.hint':  'luồng cùng lúc',
        'oauth2.textarea.placeholder':
            'Nhap moi dong: email|password\n\nVi du:\nuser@outlook.com|password123\nuser2@hotmail.com|pass456',
        'oauth2.clear':         'Xóa',
        'oauth2.copyall':       'Copy all',
        'oauth2.btn.get':       'Get OAuth2',

        // Modal
        'modal.title.default':  'Chi tiết Email',
        'modal.loading':        'Đang tải...',
        'modal.error':          'Lỗi',
        'modal.no.content':     'Không có nội dung',

        // Dynamic strings (used by app.js)
        'status.processing':    'Đang xử lý {n} tài khoản song song...',
        'status.done':          'Hoàn thành: {ok}/{total} account trong {s}s',
        'status.progress':      'Đang xử lý: {processed}/{total}',
        'summary.progress':     '0/{total} đang xử lý...',
        'summary.done':         '{ok} OK · {err} Lỗi · Tổng {total} · {s}s',
        'summary.live':         '{ok} OK · {err} Lỗi · {processed}/{total}',
        'card.waiting':         'Đang chờ...',
        'card.queued':          'Đang xếp hàng...',
        'card.reading':         'Đang đọc hòm thư...',
        'card.fallback':        'Đang thử phương thức dự phòng...',
        'card.processing.badge':'⏳ Đang chạy',
        'card.ok':              '✓ OK',
        'card.error':           '✗ Lỗi',
        'card.no.mail':         'Không có thư',
        'card.viewmore':        'Xem thêm',
        'card.loading':         'Đang tải...',
        'card.loaded':          '✓ Đã tải {n} thư',
        'card.load.error':      'Lỗi tải thêm thư',
        'btn.detail':           'Chi tiết',
        'alert.no.data':        'Chưa nhập dữ liệu hoặc sai format!',
        'alert.oauth2.empty':   'Chưa nhập email|password!',
        'alert.oauth2.format':  'Format sai! Dùng: email|password',
        'alert.oauth2.unavail': 'Tính năng Get OAuth2 không khả dụng trên Vercel deployment.',
        'oauth2.status.processing': 'Đang xử lý {i}/{n}: {email}',
        'oauth2.status.done':       'Hoàn thành {done}/{n} tài khoản',
        'oauth2.card.waiting':      '⌛ Đợi...',
        'oauth2.card.queued':       'Đang chờ trong hàng...',
        'oauth2.card.processing':   '⏳ Đang xử lý...',
        'oauth2.card.login.wait':   'Đang đăng nhập qua Playwright, vui lòng chờ...',
        'loading.text':             'Đang xử lý...',
        'line.count':               '{n} dòng',
        'friendly.loop':            '⏳ Microsoft phát hiện quá nhiều yêu cầu liên tiếp. Vui lòng chờ ~{s}s rồi thử lại.',
    },

    en: {
        // Header / Nav
        'nav.readmail':    'Read Mail',
        'nav.getoauth2':   'Get OAuth2',
        'nav.apidocs':     'API Docs',
        'nav.gitstar':     'Give me a star',
        'logo.title':      'Mail Reader',

        // Mail page — section header
        'mail.section.title':   'Enter Accounts',
        'mail.section.hint':    '(Graph API / OAuth2)',
        'mail.limit.label':     'Max emails:',
        'mail.textarea.placeholder':
            'Enter one per line: email|password|refresh_token|client_id\n\nExample:\nuser@hotmail.com|password123|M.C524_BAY.0.U.-xxxxx|9e5f94bc-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
        'mail.clear':           'Clear',
        'mail.btn.read':        'Read Inbox',
        'mail.results.title':   'Results',

        // OAuth2 page
        'oauth2.section.title': 'Get OAuth2 Token',
        'oauth2.workers.label': 'Workers:',
        'oauth2.workers.hint':  'concurrent threads',
        'oauth2.textarea.placeholder':
            'Enter one per line: email|password\n\nExample:\nuser@outlook.com|password123\nuser2@hotmail.com|pass456',
        'oauth2.clear':         'Clear',
        'oauth2.copyall':       'Copy all',
        'oauth2.btn.get':       'Get OAuth2',

        // Modal
        'modal.title.default':  'Email Details',
        'modal.loading':        'Loading...',
        'modal.error':          'Error',
        'modal.no.content':     'No content',

        // Dynamic strings
        'status.processing':    'Processing {n} accounts in parallel...',
        'status.done':          'Done: {ok}/{total} accounts in {s}s',
        'status.progress':      'Processing: {processed}/{total}',
        'summary.progress':     '0/{total} processing...',
        'summary.done':         '{ok} OK · {err} Error · Total {total} · {s}s',
        'summary.live':         '{ok} OK · {err} Error · {processed}/{total}',
        'card.waiting':         'Waiting...',
        'card.queued':          'Queued...',
        'card.reading':         'Reading inbox...',
        'card.fallback':        'Trying fallback method...',
        'card.processing.badge':'⏳ Running',
        'card.ok':              '✓ OK',
        'card.error':           '✗ Error',
        'card.no.mail':         'No messages',
        'card.viewmore':        'Load more',
        'card.loading':         'Loading...',
        'card.loaded':          '✓ Loaded {n} emails',
        'card.load.error':      'Failed to load more emails',
        'btn.detail':           'Details',
        'alert.no.data':        'No data entered or wrong format!',
        'alert.oauth2.empty':   'Please enter email|password!',
        'alert.oauth2.format':  'Wrong format! Use: email|password',
        'alert.oauth2.unavail': 'Get OAuth2 is not available on this Vercel deployment.',
        'oauth2.status.processing': 'Processing {i}/{n}: {email}',
        'oauth2.status.done':       'Done {done}/{n} accounts',
        'oauth2.card.waiting':      '⌛ Waiting...',
        'oauth2.card.queued':       'Waiting in queue...',
        'oauth2.card.processing':   '⏳ Processing...',
        'oauth2.card.login.wait':   'Logging in via Playwright, please wait...',
        'loading.text':             'Processing...',
        'line.count':               '{n} lines',
        'friendly.loop':            '⏳ Microsoft detected too many rapid requests. Please wait ~{s}s and try again.',
    }
};

// ── State ─────────────────────────────────────────────────────────────────────
let _currentLang = localStorage.getItem('lang') || 'vi';

// ── Core API ──────────────────────────────────────────────────────────────────
/**
 * Get translated string for key.
 * Supports simple template substitution: t('key', {n: 5, s: '1.2'})
 */
function t(key, vars) {
    const dict = TRANSLATIONS[_currentLang] || TRANSLATIONS['vi'];
    let str = dict[key] || TRANSLATIONS['vi'][key] || key;
    if (vars) {
        for (const [k, v] of Object.entries(vars)) {
            str = str.replaceAll(`{${k}}`, v);
        }
    }
    return str;
}

/**
 * Switch language and re-render all [data-i18n] elements.
 */
function setLang(lang) {
    if (!TRANSLATIONS[lang]) return;
    _currentLang = lang;
    localStorage.setItem('lang', lang);
    applyTranslations();
    updateLangToggle();
    // Dispatch event so app.js can react if needed
    document.dispatchEvent(new CustomEvent('langchange', { detail: { lang } }));
}

function getLang() {
    return _currentLang;
}

/**
 * Apply translations to all elements with data-i18n attribute.
 * - data-i18n="key"             → element.textContent = t(key)
 * - data-i18n-placeholder="key" → element.placeholder = t(key)
 * - data-i18n-title="key"       → element.title = t(key)
 */
function applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        el.textContent = t(key);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        el.placeholder = t(key);
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        el.title = t(key);
    });
    document.querySelectorAll('[data-i18n-html]').forEach(el => {
        const key = el.getAttribute('data-i18n-html');
        el.innerHTML = t(key);
    });
    // Update html lang attribute
    document.documentElement.lang = _currentLang;
}

/**
 * Update the lang toggle button appearance.
 */
function updateLangToggle() {
    const btn = document.getElementById('lang-toggle');
    if (!btn) return;
    btn.setAttribute('data-lang', _currentLang);
    // Update aria-label
    btn.setAttribute('aria-label', _currentLang === 'vi' ? 'Switch to English' : 'Chuyển sang Tiếng Việt');
}

/**
 * Toggle between VI and EN.
 */
function toggleLang() {
    setLang(_currentLang === 'vi' ? 'en' : 'vi');
}

// ── Auto-init on DOM ready ────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    applyTranslations();
    updateLangToggle();
});
