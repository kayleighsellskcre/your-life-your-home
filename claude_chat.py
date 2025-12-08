import os
import requests

# Get API key from environment variable
API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not API_KEY:
    print("Error: ANTHROPIC_API_KEY environment variable is not set.")
    print("Please set it using: export ANTHROPIC_API_KEY='your-api-key'")
    exit(1)

url = "https://api.anthropic.com/v1/messages"
headers = {
    "x-api-key": API_KEY,
    "content-type": "application/json",
    "anthropic-version": "2023-06-01"
}

while True:
    prompt = input("You: ")
    if prompt.lower() in ["exit", "quit"]:
        break
    data = {
        "model": "claude-sonnet-4-5-20250929",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 256
    }
    response = requests.post(url, headers=headers, json=data)
    answer = response.json()["content"][0]["text"]
    print("Claude:", answer)
