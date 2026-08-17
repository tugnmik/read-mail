import re

def is_verification_email(subject: str, body_preview: str) -> bool:
    """
    Kiểm tra xem email có phải là email chứa mã xác nhận/OTP không.
    Dùng heuristic dựa trên các từ khóa tiếng Anh và tiếng Việt.
    """
    keywords = [
        r'\bverification\b', r'\bverify\b', r'\bcode\b', r'\botp\b',
        r'mã xác nhận', r'mã xác minh', r'mã bảo mật', r'mã đăng nhập',
        r'\bactivate\b', r'\bconfirm\b', r'xác thực'
    ]
    
    text_to_check = f"{subject} {body_preview}".lower()
    
    for kw in keywords:
        if re.search(kw, text_to_check):
            return True
            
    return False

def extract_codes(subject: str, body: str, custom_pattern: str = None) -> list:
    """
    Trích xuất các mã xác nhận từ tiêu đề và nội dung email.
    Hỗ trợ 4-digit, 6-digit, 8-digit OTP, Alphanumeric, UUID, và URL.
    """
    results = []
    
    # Gom chung nội dung cần tìm kiếm
    full_text = f"{subject}\n{body}"
    
    # 1. Custom pattern (nếu có)
    if custom_pattern:
        try:
            matches = re.finditer(custom_pattern, full_text)
            for m in matches:
                val = m.group(0)
                ctx = _extract_context(full_text, m.start(), m.end())
                results.append({"type": "custom", "value": val, "context": ctx})
        except Exception:
            pass # Bỏ qua nếu custom pattern lỗi
            
    # Các regex patterns
    patterns = {
        "uuid": r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
        "otp_6": r'(?<!\d)\d{6}(?!\d)',
        "otp_8": r'(?<!\d)\d{8}(?!\d)',
        "otp_4": r'(?<!\d)\d{4}(?!\d)',
        "alphanumeric": r'\b[A-Z0-9]{5,10}\b|\b[a-zA-Z0-9]{3,}-[a-zA-Z0-9]{3,}-[a-zA-Z0-9]{3,}\b',
        "url": r'https?://[^\s<>"]*(?:verify|confirm|activate|token)[^\s<>"]*'
    }
    
    # Bộ lọc các số không phải mã xác nhận (ví dụ năm 202x)
    def is_filtered_out(val: str, type_name: str) -> bool:
        if type_name == "otp_4":
            if val.startswith("20") and int(val) in range(2000, 2040):
                return True
        return False

    for type_name, pattern in patterns.items():
        flags = re.IGNORECASE if type_name == "url" or type_name == "uuid" else 0
        matches = re.finditer(pattern, full_text, flags)
        for m in matches:
            val = m.group(0)
            if is_filtered_out(val, type_name):
                continue
                
            ctx = _extract_context(full_text, m.start(), m.end())
            
            # Tránh trùng lặp
            if not any(r['value'] == val for r in results):
                results.append({
                    "type": type_name,
                    "value": val,
                    "context": ctx
                })
                
    return results

def _extract_context(text: str, start_idx: int, end_idx: int, context_len: int = 30) -> str:
    """Lấy nội dung xung quanh mã xác nhận để hiển thị (tối đa 30 ký tự trước/sau)."""
    c_start = max(0, start_idx - context_len)
    c_end = min(len(text), end_idx + context_len)
    
    # Loại bỏ newline để context nằm trên 1 dòng
    ctx = text[c_start:c_end].replace('\n', ' ').replace('\r', '')
    return "..." + ctx.strip() + "..."

def find_best_code(subject: str, body: str, sender: str = None) -> dict:
    """
    Tìm mã xác nhận tốt nhất trong email.
    Ưu tiên: Custom (nếu truyền ngoài) > 6-digit > 4-digit/8-digit > Alphanumeric > URL.
    Ở đây sẽ ưu tiên OTP_6 vì là phổ biến nhất.
    """
    codes = extract_codes(subject, body)
    if not codes:
        return None
        
    # Trọng số ưu tiên (số càng nhỏ càng ưu tiên)
    priority = {
        "custom": 1,
        "otp_6": 2,
        "otp_4": 3,
        "otp_8": 4,
        "uuid": 5,
        "url": 6,
        "alphanumeric": 7
    }
    
    # Sắp xếp theo ưu tiên
    codes.sort(key=lambda x: priority.get(x["type"], 99))
    
    return codes[0]
