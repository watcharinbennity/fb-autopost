import os
import requests
from utils import log

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v25.0").strip()


def comment(post_id, message):
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{post_id}/comments"
    data = {
        "message": message,
        "access_token": PAGE_ACCESS_TOKEN
    }
    r = requests.post(url, data=data, timeout=60)
    r.raise_for_status()
    log("Comment posted")


def post_product(product, caption, comment_text=None):
    try:
        img = requests.get(product["image"], timeout=120)
        img.raise_for_status()

        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PAGE_ID}/photos"
        files = {"source": ("img.jpg", img.content)}
        data = {
            "caption": caption,
            "published": "true",
            "access_token": PAGE_ACCESS_TOKEN
        }

        r = requests.post(url, files=files, data=data, timeout=120)
        r.raise_for_status()

        res = r.json()
        post_id = res.get("post_id") or res.get("id")

        if post_id and comment_text:
            comment(post_id, comment_text)

        return post_id
    except Exception as e:
        log(f"Post failed: {e}")
        return None
