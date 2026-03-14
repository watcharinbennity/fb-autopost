import os
import requests
from utils import log

PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v25.0")


def comment(post_id, link):

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{post_id}/comments"

    data = {
        "message": f"🛒 สั่งซื้อสินค้า\n{link}",
        "access_token": PAGE_ACCESS_TOKEN
    }

    requests.post(url, data=data)

    log("Comment posted")


def post_product(product, caption):

    try:

        img = requests.get(product["image"]).content

        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PAGE_ID}/photos"

        files = {
            "source": ("img.jpg", img)
        }

        data = {
            "caption": caption,
            "published": "true",
            "access_token": PAGE_ACCESS_TOKEN
        }

        r = requests.post(url, files=files, data=data)

        res = r.json()

        post_id = res.get("post_id") or res.get("id")

        if post_id:
            comment(post_id, product["link"])

        return post_id

    except Exception as e:

        log(str(e))

        return None
