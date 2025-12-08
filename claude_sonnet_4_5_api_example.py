import requests

API_KEY = "***REMOVED***api03-VviSsR-dONhaG3Us7j0imY3mKB3qP1b4tGukvsf11MF6pc-0F5-DbJqKev96hB2PmVjvrINDQKqTJInZNQ-fpw-2YRGfAAA"
url = "https://api.anthropic.com/v1/messages"
headers = {
    "x-api-key": API_KEY,
    "content-type": "application/json",
    "anthropic-version": "2023-06-01"
}
data = {
    "model": "claude-sonnet-4-5-20250929",
    "messages": [{"role": "user", "content": "Hello Claude Sonnet 4.5!"}],
    "max_tokens": 256
}

response = requests.post(url, headers=headers, json=data)
print(response.json())
