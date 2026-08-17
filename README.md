# Microsoft Graph & Outlook Mail API — Multi-Adapter Integration Toolkit

[![Live Demo](https://img.shields.io/badge/Demo-Live-brightgreen?style=flat-square&logo=vercel&logoColor=white)](https://web-mail-reader.vercel.app)
![Python Version](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat-square&logo=python&logoColor=white)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
![Microsoft Graph](https://img.shields.io/badge/Microsoft%20Graph-API%20v1.0-0078D4?style=flat-square&logo=microsoft&logoColor=white)
![Outlook REST](https://img.shields.io/badge/Outlook%20REST-API%20v2.0-0078D4?style=flat-square&logo=microsoftoutlook&logoColor=white)

A Python reference implementation for integrating with Microsoft's mail APIs. This project solves several **undocumented pitfalls** developers face when working with Microsoft Graph API and Outlook REST API — including automatic token family detection, dual-API routing, and resilient fallback strategies.

Built as a fully functional web application with real-time streaming, concurrent processing, and a clean bilingual (English/Vietnamese) interface.

---

## 📌 Why This Project?

Working with Microsoft's mail APIs is deceptively complex. The official documentation doesn't cover many real-world edge cases that developers encounter in production:

| Problem | What Microsoft Docs Say | What Actually Happens |
|---------|------------------------|----------------------|
| **Token Families** | Use Microsoft Graph API | Some consumer tokens (MSA/Live) only work with Outlook REST API v2.0, not Graph. No clear documentation on which tokens map to which API. |
| **Cookie Policy** | Not mentioned | Microsoft's OAuth endpoints throw `rfc2965` / `BlockAllCookies` exceptions that silently break `requests` sessions. |
| **Scope Mismatch** | Request `Mail.Read` scope | Personal vs. Organizational tokens require different scope URIs (`graph.microsoft.com/Mail.Read` vs `outlook.office.com/Mail.Read`). Using the wrong one fails silently. |
| **Rate Limiting** | Documented throttling limits | Server-side IP blocks are common and require client-side fallback strategies — not covered in docs. |

**This project provides battle-tested solutions to all of these problems**, packaged as both a reusable service layer and a working web application.

---

## ⚙️ Technical Highlights

### 🔀 Automatic Token Family Detection & Dual-API Routing
The core innovation: `graph_api_service.py` automatically detects whether a token belongs to a **Personal (MSA)**, **Organizational (Azure AD)**, or **Live** account family, then routes the request to the correct API endpoint — Microsoft Graph API v1.0 or Outlook REST API v2.0.

```
Token Exchange → Scope Analysis → Family Detection
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
              Graph API v1.0    Outlook REST v2.0     IMAP Fallback
          (graph.microsoft.com)  (outlook.office.com)  (outlook.office365.com)
```

### ⚡ Real-Time NDJSON Streaming
Instead of waiting for all accounts to finish, results stream to the frontend as each account completes:
- **Backend:** Flask + `ThreadPoolExecutor` for concurrent processing
- **Frontend:** NDJSON (Newline Delimited JSON) streaming parser renders results instantly
- **Result:** Sub-second perceived latency (0.3–0.5s per account)

### 🔑 Smart OTP & Verification Code Extractor
Built-in heuristic extraction engine (`code_extractor.py`) that automatically parses and extracts 1-click copyable verification codes directly into the mail table and API responses:
- **Automatic prefix stripping:** Automatically strips brand/system prefixes (`G-847291` → `847291`, `FB-391024` → `391024`, `MS-123456` → `123456`) so users and automated scripts get the exact code ready for pasting.
- **Hyphenated numbers:** `883-574` (SpaceX / X.ai), `123-456`, `1234-5678`
- **Uppercase alphanumeric:** `RD4K9` (Steam Guard), `XKJHD`
- **Mixed alphanumeric:** `8F2A1K` (GitHub), `ABC-123` (Slack)
- **Standard OTP digits:** `095439`, `847291` (4–8 digits)
- **Negative filtering:** Automatically rejects orders, invoices, tracking IDs, and dictionary words (`COMMON_WORD_EXCLUSIONS`) to prevent false positives.

### 🛡️ Resilient Fallback Chain
```
Primary: Server-side Graph/Outlook API
    ↓ (if server IP is rate-limited)
FallBack 1: Client-side browser Graph API call
    ↓ (if Graph API rejects token)
Fallback 2: IMAP protocol via outlook.office365.com
```

### 🍪 Microsoft Cookie Policy Workaround
Custom `BlockAllCookies` policy prevents Microsoft's OAuth token endpoint from setting `rfc2965`-noncompliant cookies that crash Python's `http.cookiejar`:

```python
class BlockAllCookies(http.cookiejar.DefaultCookiePolicy):
    def set_ok(self, cookie, request): return False
    def return_ok(self, cookie, request): return False
```

---

## 🗂️ Project Structure

```text
├── static/
│   ├── index.html              # Web interface (bilingual EN/VI)
│   ├── styles.css              # Dark theme design system
│   ├── app.js                  # Real-time streaming UI logic & 1-click copy
│   ├── i18n.js                 # Internationalization module
│   ├── oauth2_batch.js         # Client-side batch controller
│   └── api-docs.html           # REST API documentation with code schemas
│
├── graph_api_service.py        # ⭐ Core: Dual-API client with token detection
├── code_extractor.py           # 🔑 Smart OTP & verification code extraction engine
├── web_server.py               # Flask server with NDJSON streaming endpoints
├── imap_mail_reader.py         # IMAP fallback module
├── read_mail_from_refresh.py   # CLI tool for quick token validation
├── read_mail_ui.py             # Standalone desktop client (Tkinter)
│
├── tools/
│   └── get_hotmail_token.py    # Playwright-based OAuth2 token acquisition
│
├── Dockerfile                  # Docker deployment config
├── render.yaml                 # Render deployment blueprint
├── vercel.json                 # Vercel serverless routing
└── requirements.txt            # Python dependencies
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Node.js & npm (for Vercel CLI only)

### Installation

```bash
# Clone
git clone https://github.com/tugnmik/read-mail.git
cd read-mail

# Virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start server
python web_server.py
```

Open `http://localhost:5000` in your browser.

### Input Format

```text
email|password|refresh_token|client_id
email|password|refresh_token|client_id|tenant_id   # with optional tenant
```

> The password field is retained for format compatibility but is **not used** by the API fast path — only the refresh token is required for authentication.

---

## 🌐 Deployment

### Vercel Serverless (Recommended)
Lightweight deployment as a pure API-driven mail reader (Playwright features disabled in serverless environments):

```bash
npm install -g vercel
vercel login
vercel --prod --yes
```

### Render / Docker (Full Features)
For environments that support headless browsers:

```bash
docker build -t read-mail .
docker run -p 5000:5000 read-mail
```

A `render.yaml` blueprint is included for one-click Render deployment.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
│  │ index.html│  │  app.js  │  │ i18n.js  │  │ api-docs    │ │
│  │ (UI)      │  │ (Stream) │  │ (EN/VI)  │  │ (REST Spec) │ │
│  └─────┬────┘  └─────┬────┘  └──────────┘  └─────────────┘ │
│        │  NDJSON Stream│                                     │
├────────┴──────────────┴─────────────────────────────────────┤
│                     Flask Server                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  web_server.py                                          │ │
│  │  • /api/read-mail (POST) — NDJSON streaming endpoint   │ │
│  │  • /api/get-oauth2 (POST) — Token exchange endpoint    │ │
│  │  • ThreadPoolExecutor for concurrent account processing│ │
│  └─────────────────────┬───────────────────────────────────┘ │
├────────────────────────┴────────────────────────────────────┤
│                   Service Layer                              │
│  ┌──────────────────────┐  ┌─────────────────────────────┐  │
│  │ graph_api_service.py │  │ code_extractor.py           │  │
│  │ • Token family detect│  │ • Multi-format OTP parser   │  │
│  │ • Graph API v1.0     │  │ • Contextual regex matcher  │  │
│  │ • Outlook REST v2.0  │  │ • Negative noise filters    │  │
│  │ • Cookie workaround  │  └─────────────────────────────┘  │
│  │ • Scope negotiation  │  ┌─────────────────────────────┐  │
│  └──────────────────────┘  │ imap_mail_reader.py         │  │
│                            │ • IMAP fallback & SSL/TLS   │  │
│                            └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🤝 Contributing

Contributions are welcome! Whether it's bug fixes, new API adapters, or documentation improvements.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "feat: add your feature"`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

Please follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.

---

## 🔒 Security

### Responsible Use
This project is designed for developers to manage and monitor their **own** Microsoft email accounts through legitimate OAuth2 flows. All API interactions use standard Microsoft-approved authentication mechanisms.

### Token Handling
- Tokens are processed **locally** on your machine or your own deployed server
- No credentials are stored server-side or transmitted to third parties
- You are responsible for securing your deployment environment

### Reporting Vulnerabilities
If you discover a security vulnerability, please report it responsibly by opening a private issue or contacting the maintainer directly.

---

## ⚠️ Disclaimer

This software is provided for **educational and development purposes**. It demonstrates OAuth2 integration patterns with Microsoft's identity platform.

By using this software, you acknowledge that:
1. **Account Policies:** Microsoft may restrict accounts exhibiting unusual API activity patterns.
2. **Your Responsibility:** You are solely responsible for complying with Microsoft's Terms of Service and securing your credentials.
3. **No Warranty:** The software is provided "as is", without warranty of any kind, express or implied.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## Tiếng Việt (Vietnamese Version)

<details>
<summary>Nhấn vào đây để xem tài liệu bằng Tiếng Việt</summary>

### Giới thiệu
Bộ công cụ tích hợp Microsoft Graph API và Outlook REST API cho việc đọc hộp thư Outlook/Hotmail. Dự án giải quyết nhiều vấn đề kỹ thuật **không được ghi nhận trong tài liệu chính thức** của Microsoft — bao gồm tự động nhận diện loại token, định tuyến song song hai hệ thống API, và chiến lược dự phòng đa tầng.

### Vấn đề dự án giải quyết
- **Token Family:** Token cá nhân (MSA/Live) và tổ chức (Azure AD) cần gọi API khác nhau — không có tài liệu rõ ràng
- **Cookie rfc2965:** Endpoint OAuth của Microsoft gây crash `http.cookiejar` trong Python
- **Scope URI khác biệt:** `graph.microsoft.com/Mail.Read` vs `outlook.office.com/Mail.Read` — dùng sai sẽ lỗi im lặng
- **Rate limiting:** IP bị chặn server-side cần fallback client-side — không được đề cập trong docs

### Tính năng
- **Tải nhanh (Fast Path):** Truy vấn hộp thư bằng Refresh Token, phản hồi 0.3–0.5s/tài khoản
- **Định tuyến API tự động:** Nhận diện loại token → chọn Graph API hoặc Outlook REST v2.0
- **Smart OTP Extractor:** Tự động trích xuất và lược bỏ tiền tố (ví dụ: `G-847291` → `847291`, `FB-391024` → `391024`), hỗ trợ mã số có gạch nối `883-574`, Steam Guard `RD4K9`, chữ+số `8F2A1K` kèm nút Copy 1-Click
- **Xử lý song song & Streaming:** ThreadPool + NDJSON streaming hiển thị kết quả real-time
- **Dự phòng đa tầng:** Server API → Client-side API → IMAP fallback
- **Đa ngôn ngữ:** Giao diện song ngữ Tiếng Anh / Tiếng Việt

### Cài đặt nhanh
```bash
git clone https://github.com/tugnmik/read-mail.git
cd read-mail
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python web_server.py
```
Truy cập `http://localhost:5000`.

### Cảnh báo bảo mật & Giới hạn trách nhiệm
Phần mềm này được cung cấp cho mục đích học tập và phát triển. Tác giả không chịu trách nhiệm pháp lý đối với các rủi ro phát sinh từ việc sử dụng phần mềm.

1. **Rủi ro tài khoản:** Microsoft có thể hạn chế tài khoản có hoạt động API bất thường.
2. **Bảo mật:** Token được xử lý cục bộ, bạn tự chịu trách nhiệm bảo mật môi trường triển khai.
3. **Không bảo hành:** Phần mềm được cung cấp "nguyên bản" (as-is).

</details>
