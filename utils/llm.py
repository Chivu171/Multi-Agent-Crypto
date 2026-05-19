from openai import OpenAI
from utils.config import BASE_URL, API_KEY, get_agent_config

client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY
)


def ask_llm(prompt: str, agent_name: str = "default") -> str:
    """
    Gửi prompt đến LLM Server dựa trên cấu hình riêng biệt của từng Agent.
    """
    # Lấy cấu hình model, temperature, max_tokens cho Agent tương ứng
    config = get_agent_config(agent_name)

    response = client.chat.completions.create(
        model=config["model"],
        temperature=config["temperature"],
        max_tokens=config["max_tokens"],
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content