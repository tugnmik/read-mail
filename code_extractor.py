import re

# Danh sách từ tiếng Anh/Việt thông thường cần loại trừ tuyệt đối nếu bị match nhầm
COMMON_WORD_EXCLUSIONS = {
    "below", "above", "after", "before", "email", "login", "thank", "valid",
    "address", "account", "ignore", "please", "verify", "click", "device",
    "security", "signin", "signup", "confirm", "action", "access", "update",
    "service", "support", "online", "system", "request", "message", "member",
    "duoi", "sau", "day", "xac", "nhan", "thuc", "khoan", "tai", "password",
    "one-time", "passcode", "sign-in", "two-factor", "autodesk", "welcome",
    "education", "complete", "anyone", "forward", "share", "number"
}

# Regex nhận diện các định dạng mã xác nhận theo thứ tự ưu tiên:
# 1. Mã có tiền tố: G-123456, FB-123456, MS-123456, VK-123456
# 2. Số có dấu gạch ngang: 883-574, 123-456, 1234-5678, 12-34-56
# 3. Số có khoảng trắng: 883 574, 123 456
# 4. Chữ + số có dấu gạch ngang: ABC-123, A1B-2C3, 883-574
# 5. Cụm chữ in hoa có gạch ngang: ABC-DEF
# 6. Chữ và số hỗn hợp: 8F2A1K, A1B2C3, RD4K9, 7K92X
# 7. Chuỗi chữ in hoa (như Steam Guard): XKJHD, ABCDE (4 đến 8 ký tự)
# 8. Chuỗi số thuần túy: 095439, 847291, 1234 (4 đến 8 chữ số)
CODE_PATTERN = r'\b[A-Za-z]{1,4}-\d{4,8}\b|\b\d{2,4}-\d{2,4}(?:-\d{2,4})?\b|\b\d{3,4}\s+\d{3,4}\b|\b[A-Za-z0-9]{2,4}-\d{2,6}\b|\b\d{2,6}-[A-Za-z0-9]{2,4}\b|\b[A-Z]{3,4}-[A-Z]{3,4}\b|\b(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{4,10}\b|\b[A-Z0-9]{4,8}\b|\b[0-9]{4,8}\b'

# Các mẫu tiêu đề/nội dung loại trừ (không phải email chứa mã xác nhận)
NEGATIVE_PATTERNS = [
    r'\border\s+(?:confirmation|receipt|invoice|shipped|delivered|update|placed|summary)\b',
    r'\b(?:invoice|receipt|statement|billing statement|bill|payment confirmation)\b',
    r'\bnewsletter\b',
    r'\b(?:weekly|daily|monthly)\s+(?:digest|summary|update|news)\b',
    r'\bshipping update\b',
    r'\bpackage delivered\b',
    r'\byour\s+(?:order|subscription)\s+is\s+confirmed\b',
]

# Các mẫu ngữ cảnh có độ tin cậy cao để trích xuất mã OTP trực tiếp
CONTEXTUAL_PATTERNS = [
    # Tiếng Việt (có dấu và không dấu)
    r'(?:m[ãa]\s*(?:x[áa]c\s*nh[ậa]n|x[áa]c\s*minh|otp|b[ảa]o\s*m[ậa]t|k[íi]ch\s*ho[ạa]t|[đd][ăa]ng\s*nh[ậa]p|truy\s*c[ậa]p|kh[ôo]i\s*ph[ụu]c|m[ộo]t\s*l[ầa]n)?(?:\s*c[ủu]a\s*b[ạa]n)?(?:\s*l[àa]|\s*sau\s*[đd][âa]y|\s*d[ưu][ớo]i\s*[đd][âa]y)?[\s:]+)(' + CODE_PATTERN + r')',
    r'(' + CODE_PATTERN + r')\s+l[àa]\s+m[ãa]\s+(?:[đd][ểe]\s+b[ạa]n\s+)?(?:x[áa]c\s*nh[ậa]n|x[áa]c\s*minh|otp|b[ảa]o\s*m[ậa]t|k[íi]ch\s*ho[ạa]t|[đd][ăa]ng\s*nh[ậa]p)',
    r'(?:nh[ậa]p|d[ùu]ng|s[ửu]\s*d[ụu]ng)\s+m[ãa](?:\s+sau\s*[đd][âa]y|\s+d[ưu][ớo]i\s*[đd][âa]y)?[\s:]+(' + CODE_PATTERN + r')',
    
    # Tiếng Anh
    r'(?:(?:steam\s+guard\s+code|verification|security|confirmation|validation|activation|login|access|sign-in|one-time|auth(?:entication)?)\s+code|passcode|otp)[\s:]+(?:is[\s:]+)?(' + CODE_PATTERN + r')',
    r'(' + CODE_PATTERN + r')\s+is\s+your\s+(?:[a-zA-Z0-9_\-\.]+\s+)?(?:verification|security|confirmation|validation|activation|login|access|sign-in|one-time|auth(?:entication)?)\s*(?:code|passcode|otp|pin)',
    r'(' + CODE_PATTERN + r')\s+is\s+your\s+code\b',
    r'(?:your\s+code\s+is[\s:]+|your\s+code[\s:]+)(' + CODE_PATTERN + r')',
    r'(?:enter|use|verify\s+with)(?:\s+the)?\s+code(?:\s+below)?[\s:]+(' + CODE_PATTERN + r')',
    r'(?:code|pin|passcode)[\s:]+(' + CODE_PATTERN + r')',
    r'^(' + CODE_PATTERN + r')\s+(?:is\s+your|l[àa]\s+m[ãa])',
]

# Từ khóa kiểm tra email có liên quan đến bảo mật/xác minh không
VERIFICATION_KEYWORDS = [
    r'\bverification\b', r'\bverify\b', r'\bcode\b', r'\botp\b', r'\bpasscode\b',
    r'mã xác nhận', r'ma xac nhan', r'mã xác minh', r'ma xac minh',
    r'mã bảo mật', r'ma bao mat', r'mã đăng nhập', r'ma dang nhap',
    r'mã otp', r'ma otp', r'\bsecurity code\b', r'\bconfirmation code\b',
    r'\bone-time\b', r'xác thực', r'xac thuc', r'xác nhận email', r'xac nhan email',
    r'\bvalidate\b', r'\bactivation\b', r'\bsteam guard\b'
]


def is_valid_code_value(code: str) -> bool:
    """Kiểm tra xem chuỗi trích xuất có phải là mã hợp lệ không (loại trừ từ vựng tiếng Anh)."""
    if not code:
        return False
    clean = code.strip().lower()
    raw = code.strip()
    if clean in COMMON_WORD_EXCLUSIONS:
        return False
    # Loại trừ ngày tháng YYYY-MM-DD
    if re.match(r'^20\d{2}[-/]\d{2}(?:[-/]\d{2})?$', clean):
        return False
    # Loại trừ năm 2000-2035
    if clean.isdigit() and len(clean) == 4 and 2000 <= int(clean) <= 2035:
        return False
    
    # Hợp lệ nếu:
    # 1. Có chứa ít nhất 1 chữ số
    has_digit = any(c.isdigit() for c in clean)
    # 2. Hoặc chuỗi có gạch nối VÀ có chứa số (như 883-574, ABC-123)
    has_hyphen_with_digit = '-' in clean and has_digit
    # 3. Hoặc là chuỗi in hoa hoàn toàn (như Steam Guard RD4K9 hoặc ABC-DEF) và không chứa từ cấm
    is_uppercase_code = raw.isupper() and 4 <= len(raw) <= 12 and not any(part in COMMON_WORD_EXCLUSIONS for part in clean.split('-'))
    
    if not (has_digit or has_hyphen_with_digit or is_uppercase_code):
        return False
    return True


def is_verification_email(subject: str, body_preview: str) -> bool:
    """
    Kiểm tra xem email có phải là email chứa mã xác nhận/OTP không.
    Dùng heuristic dựa trên các từ khóa và loại trừ hóa đơn/đơn hàng.
    """
    subject = subject or ""
    body = body_preview or ""
    full_text = f"{subject} {body}".lower()

    # Nếu dính từ khóa đơn hàng / hóa đơn -> Không phải
    for neg_pat in NEGATIVE_PATTERNS:
        if re.search(neg_pat, full_text):
            return False

    # Kiểm tra từ khóa xác minh
    for kw in VERIFICATION_KEYWORDS:
        if re.search(kw, full_text):
            return True

    return False


def _clean_html_to_text(html_content: str) -> str:
    """Làm sạch HTML thành văn bản thuần, loại bỏ tags và entities để tìm mã chuẩn xác."""
    if not html_content:
        return ""
    if "<" not in html_content and ">" not in html_content:
        return html_content
    # Loại bỏ script & style
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html_content, flags=re.DOTALL | re.IGNORECASE)
    # Chuyển thẻ xuống dòng/khối thành khoảng trắng/xuống dòng
    text = re.sub(r'<(br|p|div|tr|h[1-6]|li)[^>]*>', '\n', text, flags=re.IGNORECASE)
    # Loại bỏ các thẻ HTML còn lại
    text = re.sub(r'<[^>]+>', ' ', text)
    # Giải mã các ký tự HTML entities cơ bản
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    # Gộp khoảng trắng liên tiếp
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()


def clean_code_value(code: str) -> str:
    """
    Loại bỏ các tiền tố thương hiệu như G-, FB-, MS-, VK-, TG- để người dùng copy trực tiếp mã số thực tế.
    Ví dụ: G-847291 -> 847291, FB-391024 -> 391024, MS-123456 -> 123456.
    """
    if not code:
        return ""
    code = code.strip()
    m = re.match(r'^[A-Za-z]{1,4}[-\s:]+(\d{4,8})$', code)
    if m:
        return m.group(1)
    return code


def find_best_code(subject: str, body: str, sender: str = None) -> dict:
    """
    Tìm mã xác nhận tốt nhất trong email theo ngữ cảnh.
    Tự động xử lý cả tiêu đề, body preview và toàn bộ nội dung HTML dài.
    Hỗ trợ dạng số có gạch nối (883-574), tiền tố (G-123456 -> 123456, FB-123456 -> 123456), chữ+số (A1B2C3).
    """
    subject = subject or ""
    body = _clean_html_to_text(body or "")
    full_text = f"{subject}\n{body}"
    subject_lower = subject.lower()

    # 1. Loại trừ nếu là email đơn hàng, hóa đơn, newsletter
    for neg_pat in NEGATIVE_PATTERNS:
        if re.search(neg_pat, subject_lower):
            return None

    # 2. Khớp theo mẫu ngữ cảnh có độ tin cậy cao
    for pat in CONTEXTUAL_PATTERNS:
        for m in re.finditer(pat, full_text, re.IGNORECASE | re.MULTILINE):
            code = m.group(1).strip()
            if is_valid_code_value(code):
                final_code = clean_code_value(code)
                return {"type": "code", "value": final_code, "context": _extract_context(full_text, m.start(), m.end())}

    # 3. Nếu email có từ khóa xác minh, tìm mã gần từ khóa
    VERIFY_KW = ['code', 'mã', 'otp', 'verify', 'xác', 'passcode', 'security', 'pin', 'bảo mật', 'one-time', 'đăng nhập', 'login', 'confirm', 'kích hoạt', 'activation', 'validate']
    has_verify = any(re.search(r'\b' + re.escape(kw) + r'\b', full_text, re.IGNORECASE) for kw in VERIFY_KW) or any(k in subject_lower for k in ['xác', 'mã', 'code', 'otp', 'security', 'confirm', 'validate'])
    
    if has_verify:
        matches = re.finditer(CODE_PATTERN, full_text, re.IGNORECASE)
        for om in matches:
            val = om.group(0).strip()
            if not is_valid_code_value(val):
                continue
            start, end = om.start(), om.end()
            surrounding = full_text[max(0, start - 120):min(len(full_text), end + 120)].lower()

            # Loại trừ nếu gần đơn hàng, địa chỉ, ngày tháng, tiền tệ
            if re.search(r'\b(order|invoice|tracking|suite|apt|box|port|address|price|\$|usd|vnd|₫)\b', surrounding):
                continue

            # Bắt buộc xung quanh phải có từ khóa gợi ý mã OTP
            if any(k in surrounding for k in VERIFY_KW):
                final_code = clean_code_value(val)
                return {"type": "code", "value": final_code, "context": _extract_context(full_text, start, end)}

    return None


def extract_codes(subject: str, body: str, custom_pattern: str = None) -> list:
    """
    Trích xuất danh sách mã xác nhận từ email.
    """
    subject = subject or ""
    body = body or ""
    full_text = f"{subject}\n{body}"
    results = []

    # 1. Custom pattern
    if custom_pattern:
        try:
            matches = re.finditer(custom_pattern, full_text)
            for m in matches:
                val = m.group(0)
                ctx = _extract_context(full_text, m.start(), m.end())
                results.append({"type": "custom", "value": val, "context": ctx})
        except Exception:
            pass

    # 2. Best contextual code
    best = find_best_code(subject, body)
    if best and not any(r["value"] == best["value"] for r in results):
        results.append(best)

    return results


def _extract_context(text: str, start_idx: int, end_idx: int, context_len: int = 30) -> str:
    """Lấy nội dung xung quanh mã để hiển thị ngữ cảnh."""
    c_start = max(0, start_idx - context_len)
    c_end = min(len(text), end_idx + context_len)
    ctx = text[c_start:c_end].replace('\n', ' ').replace('\r', '')
    return "..." + ctx.strip() + "..."

