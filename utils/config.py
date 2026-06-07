# utils/config.py

import os
from dotenv import load_dotenv

# Load các biến môi trường từ file .env
load_dotenv()

# ── OpenRouter ────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL_NAME = os.getenv("OPENROUTER_MODEL_NAME", "openai/gpt-oss-120b:free")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://localhost:8501")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "Multi-Agent-Crypto")

# ── LM Studio (fallback local) ────────────────────────────────────────────────
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:1234/v1")
API_KEY = os.getenv("API_KEY", "lm-studio")

# Cấu hình chi tiết cho từng Agent trong hệ thống
# Model dùng chung OPENROUTER_MODEL_NAME, chỉ khác temperature/max_tokens
AGENT_LLM_CONFIGS = {
    "financial": {
        "model": OPENROUTER_MODEL_NAME,
        "temperature": 0.1,  # Phân tích tài chính cần độ chính xác cao, ít sáng tạo
        "max_tokens": 1500
    },
    "market": {
        "model": OPENROUTER_MODEL_NAME,
        "temperature": 0.2,  # Nhận định kỹ thuật cần bám sát chỉ số
        "max_tokens": 1500
    },
    "sentiment": {
        "model": OPENROUTER_MODEL_NAME,
        "temperature": 0.4,  # Nhận định mạng xã hội có thể sáng tạo nhẹ
        "max_tokens": 1200
    },
    "validator": {
        "model": OPENROUTER_MODEL_NAME,
        "temperature": 0.0,  # Thẩm định và phát hiện lỗi logic cần tính deterministic tuyệt đối
        "max_tokens": 1500
    },
    "mediator": {
        "model": OPENROUTER_MODEL_NAME,
        "temperature": 0.3,  # Điều phối và tổng hợp ý kiến cần sự cân bằng
        "max_tokens": 2000
    },
    "default": {
        "model": OPENROUTER_MODEL_NAME,
        "temperature": 0.2,
        "max_tokens": 1000
    }
}

def get_agent_config(agent_name: str) -> dict:
    """
    Helper function để lấy cấu hình LLM cho một agent cụ thể.
    Nếu agent_name không tồn tại, sẽ trả về cấu hình mặc định (default).
    """
    return AGENT_LLM_CONFIGS.get(agent_name.lower(), AGENT_LLM_CONFIGS["default"])
