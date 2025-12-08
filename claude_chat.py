import requests

API_KEY = "***REMOVED***R2sqO_vfKzgxlr7Qc6Ogyf3-H1ZiVV-N16IyyH8JllfWHBq0g1VYWERrbjavnooltpwAIXt1m-kB7z0d49Q-kCffegAA"
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
