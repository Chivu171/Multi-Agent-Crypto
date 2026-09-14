# utils/retry.py

"""Chính sách retry dùng chung cho toàn bộ dự án — một nơi duy nhất định
nghĩa "thử lại bao nhiêu lần, chờ bao lâu, với loại lỗi nào" để tránh mỗi
file tự chọn tham số khác nhau.

- `http_retry`: cho các lệnh gọi `requests.get(...)` tới API bên ngoài
  (Binance, blockchain.info, Alternative.me, ForexFactory) — retry khi có
  lỗi mạng/HTTP tạm thời (timeout, 429, 5xx qua `raise_for_status()`).
- `llm_retry`: cho lệnh gọi LLM qua OpenAI SDK (OpenRouter/Groq/LM Studio)
  — chỉ retry khi lỗi rate-limit hoặc lỗi kết nối tạm thời, KHÔNG retry lỗi
  cấu hình sai (401/400) vì thử lại cũng sẽ fail y hệt, chỉ tốn thời gian.
"""

import requests
from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True,
)

llm_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError)),
    reraise=True,
)
