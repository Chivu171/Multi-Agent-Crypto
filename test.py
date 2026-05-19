from utils.llm import ask_llm


response = ask_llm(
    "Analyze BTC sentiment in one sentence."
)

print(response)