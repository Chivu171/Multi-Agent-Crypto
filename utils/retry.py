# utils/retry.py

"""Chính sách retry dùng chung cho toàn bộ dự án — một nơi duy nhất định
nghĩa "thử lại bao nhiêu lần, chờ bao lâu, với loại lỗi nào" để tránh mỗi
file tự chọn tham số khác nhau.

- `http_retry`: cho các lệnh gọi `requests.get(...)` tới API bên ngoài
  (Binance, blockchain.info, Alternative.me, ForexFactory) — retry khi có
  lỗi mạng/HTTP tạm thời (timeout, 429, 5xx qua `raise_for_status()`).
- Lệnh gọi LLM dùng chính sách riêng trong `utils/llm.py` (`_create_completion`):
  phân biệt quota với rate-limit và giới hạn theo thời gian của cả lượt chạy.
"""

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True,
)

