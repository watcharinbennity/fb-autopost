import json
from datetime import datetime


def log_post(mode: str, topic: str = "", image: str = "", product: dict | None = None, post_id: str | None = None) -> None:
    row = {
        "time": str(datetime.now()),
        "mode": mode,
        "topic": topic,
        "image": image,
        "post_id": post_id or "",
        "product": product or {},
    }

    try:
        with open("posted_log.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                data = []
    except Exception:
        data = []

    data.append(row)

    with open("posted_log.json", "w", encoding="utf-8") as f:
        json.dump(data[-1000:], f, ensure_ascii=False, indent=2)
