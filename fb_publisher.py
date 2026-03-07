import os
import requests

PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
TIMEOUT = 30


def publish_post(caption: str, image_path: str) -> str | None:
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    with open(image_path, "rb") as f:
        response = requests.post(
            url,
            files={"source": f},
            data={
                "caption": caption,
                "access_token": PAGE_ACCESS_TOKEN,
            },
            timeout=TIMEOUT,
        )

    try:
        data = response.json()
        print(data, flush=True)
        return data.get("post_id")
    except Exception:
        return None


def comment_product(post_id: str, link: str) -> None:
    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"

    try:
        response = requests.post(
            url,
            data={
                "message": f"🛒 สั่งซื้อสินค้า\n{link}",
                "access_token": PAGE_ACCESS_TOKEN,
            },
            timeout=TIMEOUT,
        )
        print(response.json(), flush=True)
    except Exception as e:
        print(f"COMMENT ERROR: {e}", flush=True)
