import requests
from utils import log


def comment(post_id, access_token, message, graph_api_version="v25.0"):
    url = f"https://graph.facebook.com/{graph_api_version}/{post_id}/comments"
    data = {
        "message": message,
        "access_token": access_token
    }
    r = requests.post(url, data=data, timeout=60)
    r.raise_for_status()
    log("Comment posted")


def post_product(page_id, access_token, product, caption, comment_text=None, graph_api_version="v25.0"):
    try:
        log(f"Downloading image for post: {product['title'][:80]}")
        img = requests.get(product["image"], timeout=(20, 60))
        img.raise_for_status()

        url = f"https://graph.facebook.com/{graph_api_version}/{page_id}/photos"
        files = {"source": ("img.jpg", img.content)}
        data = {
            "caption": caption,
            "published": "true",
            "access_token": access_token
        }

        log(f"Posting to page_id={page_id}")
        r = requests.post(url, files=files, data=data, timeout=(20, 120))
        r.raise_for_status()

        res = r.json()
        post_id = res.get("post_id") or res.get("id")

        if post_id and comment_text:
            comment(post_id, access_token, comment_text, graph_api_version=graph_api_version)

        return post_id
    except Exception as e:
        log(f"Post failed: {e}")
        return None
