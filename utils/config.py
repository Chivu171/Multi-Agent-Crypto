# utils/config.py

import os
from dotenv import load_dotenv

# Load các biến môi trường từ file .env
load_dotenv()

# Cấu hình kết nối LLM Server
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:1234/v1")
API_KEY = os.getenv("API_KEY", "lm-studio")

# Cấu hình chi tiết cho từng Agent trong hệ thống
AGENT_LLM_CONFIGS = {
    "financial": {
        "model": os.getenv("FINANCIAL_AGENT_MODEL", "google/gemma-4-e4b"),
        "temperature": 0.1,  # Phân tích tài chính cần độ chính xác cao, ít sáng tạo
        "max_tokens": 1500
    },
    "market": {
        "model": os.getenv("MARKET_AGENT_MODEL", "google/gemma-4-e4b"),
        "temperature": 0.2,  # Nhận định kỹ thuật cần bám sát chỉ số
        "max_tokens": 1500
    },
    "sentiment": {
        "model": os.getenv("SENTIMENT_AGENT_MODEL", "google/gemma-4-e4b"),
        "temperature": 0.4,  # Nhận định mạng xã hội có thể sáng tạo nhẹ
        "max_tokens": 1200
    },
    "validator": {
        "model": os.getenv("VALIDATOR_AGENT_MODEL", "google/gemma-4-e4b"),
        "temperature": 0.0,  # Thẩm định và phát hiện lỗi logic cần tính deterministic tuyệt đối
        "max_tokens": 1500
    },
    "mediator": {
        "model": os.getenv("MEDIATOR_AGENT_MODEL", "google/gemma-4-e4b"),
        "temperature": 0.3,  # Điều phối và tổng hợp ý kiến cần sự cân bằng
        "max_tokens": 2000
    },
    "default": {
        "model": os.getenv("DEFAULT_MODEL", "google/gemma-4-e4b"),
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
