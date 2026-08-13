# Outlook & Hotmail Multi-Account Mail Reader

[![Live Demo](https://img.shields.io/badge/Demo-Live-brightgreen?style=flat-square&logo=vercel&logoColor=white)](https://web-mail-reader.vercel.app)
![Python Version](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat-square&logo=python&logoColor=white)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

A lightweight web application for fetching and reading inboxes of multiple Outlook/Hotmail accounts concurrently. It utilizes Microsoft Graph API and Outlook Rest API via OAuth2 Refresh Tokens.

This project is optimized for performance, featuring parallel execution, real-time streaming, and resilient fallback mechanisms.

---

## Language / Ngôn ngữ
* [Vietnamese Version (Tiếng Việt)](#tiếng-việt-vietnamese-version)

---

## Features

- **Fast Path Queries:** Directly requests mail lists using cached refresh/access tokens, averaging 0.3s to 0.5s per account.
- **Automatic API Routing:** Automatically detects the token family (Personal, Organizational, or Live) and routes queries to Microsoft Graph API or Outlook API v2.0.
- **Parallel Processing & Streaming:** 
  - Backend handles accounts concurrently using a thread pool.
  - Frontend renders results in real-time using NDJSON (Newline Delimited JSON) streaming as soon as each individual account is processed.
- **Resilient Fallbacks:**
  - Strict cookie policy implementation to prevent Microsoft `BlockAllCookies` / `rfc2965` exceptions.
  - Supports browser-side Graph API queries if the backend server's IP is flagged or rate-limited by Microsoft.
- **Optional Batch Token Acquisition:**
  - Includes a Playwright automation script to programmatically log into Microsoft accounts and harvest refresh tokens from an `email|password` list.
  - Implements stagged workers to minimize rate-limiting and IP blocks during automated logins.

---

## Project Structure

```text
├── static/
│   ├── index.html          # Web interface
│   ├── styles.css          # Design system stylesheet
│   ├── app.js              # Real-time mail loading and UI logic
│   ├── oauth2_batch.js     # Client-side batch controller for tokens
│   └── api-docs.html       # API specification documentation
├── web_server.py           # Flask server entrypoint and route handlers
├── graph_api_service.py    # Microsoft Graph and Outlook API client layer
├── imap_mail_reader.py     # Fallback IMAP helper module
├── get_hotmail_token.py    # Playwright browser automation script
├── read_mail_from_refresh.py # Independent CLI tool for token checking
├── read_mail_ui.py         # Standalone desktop client (Tkinter)
├── requirements.txt        # Python dependency manifest
├── Dockerfile              # Docker image configuration
├── render.yaml             # Render deployment blueprint
└── vercel.json             # Vercel Serverless routing blueprint
```

---

## Input Specifications

### 1. Mail Reader Tab
Accepts accounts in the following format (one per line):
```text
email|password|refresh_token|client_id
```
Or with an optional Tenant ID:
```text
email|password|refresh_token|client_id|tenant_id
```
*Note: The password field is kept for format consistency but is bypassed by the Graph API fast path.*

### 2. Token Generator Tab
Accepts credentials to run the Playwright browser automation (one per line):
```text
email|password
```

---

## Installation & Local Setup

### Prerequisites
- Python 3.8 or higher
- Node.js & npm (for Vercel CLI deployments only)

### Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/tugnmik/read-mail.git
   cd read-mail
   ```

2. **Set up a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers:**
   ```bash
   playwright install chromium
   ```

5. **Start the local server:**
   ```bash
   python web_server.py
   ```
   Open `http://localhost:5000` in your web browser.

---

## Deployment

### 1. Vercel Serverless (Recommended)
Since Vercel's serverless environment does not support Playwright's heavy browser binaries, the **Get OAuth2** tab is disabled on this platform. The application operates purely as a fast mail reader.

Deploy instantly using the Vercel CLI:
```bash
npm install -g vercel
vercel login
vercel --prod --yes
```

### 2. Render (Full Features)
Render supports Docker environments, allowing you to run the Playwright automation along with the web server.

- A `Dockerfile` is provided, setting up Python, headless Google Chrome, and all required system libraries.
- Create a **Web Service** on Render and connect it to your repository. It will automatically load the configuration from `render.yaml`.

---

## Disclaimer & Security Warning

### Educational Purposes Only
This software is provided for educational and testing purposes only. It is intended to help developers understand OAuth2 flows and Microsoft Graph API integrations.

### Limitation of Liability
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT, OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE. 

By running this software, you acknowledge that:
1. **Account Suspension Risk:** Microsoft may flag, restrict, or suspend accounts that exhibit unusual API activities, high-frequency requests, or programmatic logins via automated browsers (Playwright).
2. **Credential Handling:** The application processes your emails, passwords, and tokens locally or on your deployed server instances. You are solely responsible for securing your hosting environment and environment variables. Do not share raw tokens or output files containing credentials.
3. **No Warranty:** The software is provided "as is", without warranty of any kind, express or implied.

---

## License

This project is licensed under the MIT License. See the LICENSE file (if any) or standard MIT terms for details.

---

## Tiếng Việt (Vietnamese Version)

<details>
<summary>Nhấn vào đây để xem tài liệu bằng Tiếng Việt</summary>

### Giới thiệu
Ứng dụng web gọn nhẹ dùng để đọc hộp thư đến (Inbox) của nhiều tài khoản Outlook/Hotmail cùng lúc qua Microsoft Graph API và Outlook Rest API sử dụng OAuth2 Refresh Token. Dự án được tối ưu hóa hiệu năng, xử lý song song thời gian thực và tự động chuyển đổi API linh hoạt.

### Tính năng
- **Tải nhanh (Fast Path):** Truy vấn hộp thư bằng Refresh Token/Access Token có sẵn, thời gian phản hồi từ 0.3s đến 0.5s cho mỗi tài khoản.
- **Định tuyến API tự động:** Nhận diện loại tài khoản và tự động chọn Microsoft Graph hoặc Outlook Rest API v2.0 để gửi yêu cầu.
- **Xử lý song song & Streaming:** Kết hợp ThreadPool ở Backend và NDJSON Streaming ở Frontend để hiển thị kết quả ngay khi tài khoản tương ứng xử lý xong.
- **Dự phòng lỗi:** Thiết lập chính sách cookie nghiêm ngặt để triệt tiêu lỗi `rfc2965` của Microsoft. Cho phép gọi API trực tiếp từ trình duyệt nếu IP máy chủ bị chặn.
- **Lấy Token tự động (Tùy chọn):** Kịch bản Playwright giả lập trình duyệt để lấy Refresh Token tự động từ danh sách `email|password`.

### Định dạng đầu vào
1. **Đọc Mail:** `email|password|refresh_token|client_id` (hoặc có thêm `|tenant_id` ở cuối).
2. **Get OAuth2:** `email|password`.

### Cài đặt cục bộ
1. Clone repo: `git clone https://github.com/tugnmik/read-mail.git`
2. Tạo môi trường ảo: `python -m venv .venv` và kích hoạt (`.venv\Scripts\activate`).
3. Cài đặt thư viện: `pip install -r requirements.txt`.
4. Cài đặt trình duyệt Playwright: `playwright install chromium`.
5. Khởi chạy: `python web_server.py`. Truy cập `http://localhost:5000`.

### Cảnh báo bảo mật & Giới hạn trách nhiệm
Phần mềm này được cung cấp hoàn toàn cho mục đích học tập và thử nghiệm. Tác giả không chịu bất kỳ trách nhiệm pháp lý nào đối với các thiệt hại, rủi ro phát sinh từ việc sử dụng phần mềm. 

Khi sử dụng ứng dụng, bạn đồng ý rằng:
1. **Rủi ro khóa tài khoản:** Microsoft có thể quét và tạm khóa các tài khoản có hành vi đăng nhập tự động bằng trình duyệt ảo hoặc gửi yêu cầu API với tần suất lớn.
2. **Bảo mật thông tin:** Tài khoản và token được xử lý trực tiếp trên máy của bạn hoặc server bạn tự deploy. Bạn tự chịu trách nhiệm bảo mật môi trường chạy ứng dụng, không chia sẻ file chứa token hay mật khẩu.
3. **Không bảo hành:** Phần mềm được cung cấp dưới dạng "nguyên bản" (as-is), không có bất kỳ cam kết hay bảo hành nào về độ ổn định.

</details>
