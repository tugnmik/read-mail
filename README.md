# 📧 Outlook & Hotmail Multi-Account Mail Reader (Graph API & OAuth2)

Hệ thống web-app tối ưu và hiệu năng cao giúp đọc hộp thư đến (Inbox) của nhiều tài khoản Outlook/Hotmail đồng thời qua **Microsoft Graph API / Outlook Rest API** bằng phương pháp **OAuth2 Refresh Token**. 

Ứng dụng được thiết kế tối giản, tải dữ liệu song song cực nhanh, xử lý lỗi mượt mà và có thể chạy được trên nhiều môi trường đám mây (Render, Vercel, Docker) hoặc máy cá nhân.

---

## 🌟 Tính Năng Nổi Bật

- **⚡ Tốc độ siêu tốc (Fast Path):** Sử dụng trực tiếp refresh_token hoặc access_token có sẵn để truy vấn API của Microsoft, thời gian tải thư trung bình chỉ **0.3s - 0.5s/account**.
- **🔄 Cơ chế tự động nhận dạng API (Auto-API Detection):** Tự động phát hiện loại tài khoản (Personal / Business / Live cũ) và chuyển đổi linh hoạt giữa Microsoft Graph API và Outlook API v2.0 để tránh lỗi quyền.
- **🚀 Xử lý song song thông minh (Concurrency & Streaming):**
  - Backend sử dụng `ThreadPoolExecutor` để chạy nhiều luồng cùng lúc.
  - Sử dụng **NDJSON Streaming** để truyền tải kết quả trực tiếp (real-time) về giao diện. Tài khoản nào xử lý xong sẽ hiển thị ngay lập tức, không cần đợi toàn bộ danh sách tải xong.
- **🛡️ Cơ chế Dự phòng & Bypass:**
  - Tích hợp kiểm soát cookie chặt chẽ để loại bỏ lỗi cookie (`rfc2965`).
  - Hỗ trợ lấy lại token trực tiếp từ phía client (Fallback) nếu IP của server backend bị Microsoft chặn.
- **🔑 Công cụ tự động lấy OAuth2 Token (Playwright Batch Automation):**
  - Chức năng tự động hóa đăng nhập trình duyệt ảo (Playwright) để thu thập mã Refresh Token từ danh sách `email|password`.
  - Hỗ trợ phân luồng chạy đồng thời (multi-workers) và giãn cách thời gian (staggering) thông minh để tránh dính spam/block IP từ Microsoft.
- **💻 Giao diện hiện đại & Premium:** Thiết kế Responsive, hỗ trợ chế độ Dark Mode, hiệu ứng tải mượt mà, xem chi tiết thư trong Sandbox Iframe an toàn.

---

## 🛠️ Công Nghệ Sử Dụng

- **Backend:** Python, Flask, Gunicorn/Waitress, Requests (Connection Pooling).
- **Automation:** Playwright (Python).
- **Frontend:** Vanilla HTML5, CSS3 (Rich custom design system), Modern Vanilla Javascript.
- **Deployment:** Docker, Render config (`render.yaml`), Vercel Serverless (`vercel.json`).

---

## 📂 Cấu Trúc Thư Mục

```text
├── static/
│   ├── index.html          # Giao diện chính của ứng dụng
│   ├── styles.css          # CSS thiết kế giao diện (Dark/Light responsive)
│   ├── app.js              # Logic đọc thư và cập nhật thời gian thực
│   ├── oauth2_batch.js     # Logic điều khiển luồng lấy token tự động
│   └── api-docs.html       # Tài liệu mô tả chi tiết các API endpoint
├── web_server.py           # Flask backend server & endpoints
├── graph_api_service.py    # Tầng xử lý logic kết nối Microsoft Graph/Outlook API
├── imap_mail_reader.py     # Module hỗ trợ đọc IMAP (nếu cấu hình)
├── get_hotmail_token.py    # Kịch bản tự động hóa Playwright lấy Refresh Token
├── read_mail_from_refresh.py # Kịch bản CLI chạy độc lập đọc thư bằng token
├── read_mail_ui.py         # Giao diện desktop (Tkinter) chạy offline
├── requirements.txt        # Danh sách thư viện Python phụ thuộc
├── Dockerfile              # Cấu hình container hóa ứng dụng
├── render.yaml             # Cấu hình deploy tự động lên Render
└── vercel.json             # Cấu hình deploy serverless lên Vercel
```

---

## 📋 Định Dạng Dữ Liệu Đầu Vào

### 1. Tại tab "Đọc Mail"
Định dạng nhập (mỗi dòng một tài khoản):
```text
email|password|refresh_token|client_id
```
*Hoặc định dạng nâng cao với Tenant ID:*
```text
email|password|refresh_token|client_id|tenant_id
```
*(Ghi chú: Trường `password` được giữ lại để đồng bộ định dạng dữ liệu, luồng Fast Path Graph API sẽ bỏ qua mật khẩu này).*

### 2. Tại tab "Get OAuth2"
Định dạng nhập để chạy tool tự động lấy token:
```text
email|password
```

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Môi Trường Cục Bộ (Local)

### Yêu cầu hệ thống
- Python 3.8 trở lên
- Node.js & npm (nếu muốn deploy bằng Vercel CLI)

### Các bước cài đặt

1. **Clone repository về máy:**
   ```bash
   git clone https://github.com/tugnmik/read-mail.git
   cd read-mail
   ```

2. **Khởi tạo và kích hoạt môi trường ảo (Virtual Environment):**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Cài đặt các thư viện phụ thuộc:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Cài đặt môi trường duyệt trình duyệt của Playwright:**
   ```bash
   playwright install chromium
   ```

5. **Chạy server phát triển (Development Server):**
   ```bash
   python web_server.py
   ```
   Ứng dụng sẽ chạy tại địa chỉ: `http://localhost:5000`

---

## ☁️ Hướng Dẫn Deploy Lên Đám Mây

### 1. Deploy lên Vercel (Khuyên dùng - Nhanh & Miễn phí)
Do môi trường Serverless của Vercel không hỗ trợ cài đặt các gói trình duyệt nặng như Playwright, tính năng **Get OAuth2** (chạy Playwright tự động) sẽ được ẩn đi. Ứng dụng sẽ tập trung tối đa hiệu năng vào chức năng đọc mail.

**Cách deploy bằng Vercel CLI:**
```bash
# Cài đặt vercel cli
npm install -g vercel

# Đăng nhập vào tài khoản Vercel
vercel login

# Deploy lên Production
vercel --prod --yes
```
*Cấu hình định tuyến và python runtime đã được định nghĩa sẵn trong file `vercel.json`.*

### 2. Deploy lên Render (Hỗ trợ đầy đủ tất cả tính năng)
Render hỗ trợ Docker container hoàn chỉnh, cho phép chạy được cả Flask backend và công cụ lấy token tự động qua Playwright.

- Ứng dụng đã có sẵn file `Dockerfile` cài đặt đầy đủ Python, Google Chrome và các thư viện cần thiết.
- Bạn chỉ cần liên kết Repository này với tài khoản Render của bạn và tạo một **Web Service**. Render sẽ tự động cấu hình qua tệp `render.yaml`.

---

## 🔒 Khuyến Nghị Bảo Mật

- **Không chia sẻ công khai** các file text chứa danh sách tài khoản đã có cấu trúc đầy đủ token (`_last_token.txt` hoặc các file txt tự xuất bản). Tệp `.gitignore` của dự án đã được thiết lập để bỏ qua các file debug, log và các tệp lưu token cục bộ.
- Nên sử dụng ứng dụng ở chế độ riêng tư hoặc tự deploy lên máy chủ cá nhân để đảm bảo an toàn thông tin tài khoản Microsoft của bạn.
