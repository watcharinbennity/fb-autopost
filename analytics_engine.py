import json

LOG_FILE = "post_log.json"


def load_logs():
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def analyze_posts():
    logs = load_logs()
    stats = {}

    for log in logs:
        t = log.get("type", "unknown")
        stats[t] = stats.get(t, 0) + 1

    return stats
