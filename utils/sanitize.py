# utils/sanitize.py

"""Lớp phòng vệ tối thiểu chống prompt injection từ dữ liệu ngoài (tin tức,
on-chain summary, market summary) trước khi nhét vào prompt LLM.

Đây KHÔNG phải là giải pháp triệt để (không có sandbox nào chống injection
100%) — chỉ là lớp lọc rẻ, bổ sung cho delimiter rõ ràng trong
`utils/prompts.py`. Hai lớp cùng dùng: delimiter đánh dấu ranh giới dữ liệu,
sanitize loại bỏ các cụm giả lệnh phổ biến nhất.
"""

import re

# Các cụm thường dùng để "vượt rào" chỉ thị hệ thống trong prompt injection.
# So khớp không phân biệt hoa/thường, cho phép khoảng trắng linh hoạt.
_INSTRUCTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"bỏ\s+qua\s+(mọi\s+|các\s+)?(chỉ\s*thị|hướng\s*dẫn)\s*(trước|ở trên)?",
    r"system\s*:\s*",
    r"assistant\s*:\s*",
    r"you\s+are\s+now\s+",
    r"new\s+instructions?\s*:",
    r"#{2,}",  # ### heading-style injection markers
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _INSTRUCTION_PATTERNS]

_REDACTED = "[LỌC BỎ - NGHI NGỜ CHỈ THỊ ẨN]"


def strip_instruction_patterns(text: str) -> str:
    """Thay thế các cụm giống chỉ thị hệ thống bằng placeholder.

    Không làm mất nội dung tổng thể (không xoá cả đoạn), chỉ vô hiệu hoá
    cụm từ nghi vấn để LLM không hiểu nhầm đó là chỉ thị mới.
    """
    if not text:
        return text

    cleaned = text
    for pattern in _COMPILED_PATTERNS:
        cleaned = pattern.sub(_REDACTED, cleaned)
    return cleaned
