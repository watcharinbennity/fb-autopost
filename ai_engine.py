import os
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TIMEOUT = 20


def ask_ai(prompt: str) -> str | None:
    if not OPENAI_API_KEY:
        return None

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4.1-mini",
                "input": prompt,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data["output"][0]["content"][0]["text"].strip()
    except Exception as e:
        print(f"AI ERROR: {e}", flush=True)
        return None
