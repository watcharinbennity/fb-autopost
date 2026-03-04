import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


GRAPH_BASE = "https://graph.facebook.com/v25.0"


@dataclass
class PostItem:
    image_url: str
    caption: str


def must_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env: {name}")
    return v


def load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_posts(raw: Any) -> List[PostItem]:
    if not isinstance(raw, list):
        raise RuntimeError("posts.json must be a JSON array")
    out: List[PostItem] = []
    for i, it in enumerate(raw):
        if not isinstance(it, dict):
            raise RuntimeError(f"posts.json item #{i} must be object")
        image_url = (it.get("image_url") or "").strip()
        caption = (it.get("caption") or "").strip()
        if not image_url:
            raise RuntimeError(f"posts.json item #{i} missing image_url")
        if not caption:
            # ยังอนุญาต caption ว่างได้ แต่ของคุณต้องการมีข้อความก็ใส่ไว้
            caption = ""
        out.append(PostItem(image_url=image_url, caption=caption))
    return out


def pick_next_post(posts: List[PostItem], state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    idx = int(state.get("next_index", 0))
    if idx >= len(posts):
        return None
    return {"index": idx, "post": posts[idx]}


def post_photo(page_id: str, page_token: str, item: PostItem) -> Dict[str, Any]:
    url = f"{GRAPH_BASE}/{page_id}/photos"

    # โพสต์ “รูป” แบบให้ FB ไปดึงจาก URL
    # สำคัญ: image_url ต้องเป็นลิงก์ไฟล์รูปตรงๆ (ลงท้าย .jpg/.png) และเข้าถึงได้แบบ public
    payload = {
        "url": item.image_url,
        "caption": item.caption,
        "published": "true",
        "access_token": page_token,
    }

    r = requests.post(url, data=payload, timeout=60)
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"Facebook response not JSON: HTTP {r.status_code} {r.text[:300]}")

    if r.status_code >= 400 or "error" in data:
        raise RuntimeError(f"Facebook API error: HTTP {r.status_code} {json.dumps(data, ensure_ascii=False)}")

    return data


def main() -> int:
    page_id = must_env("FB_PAGE_ID")
    page_token = must_env("FB_PAGE_ACCESS_TOKEN")
    posts_file = os.getenv("POSTS_FILE", "posts.json")
    state_file = os.getenv("STATE_FILE", "state.json")

    raw_posts = load_json(posts_file, default=[])
    posts = normalize_posts(raw_posts)
    if not posts:
        print("No posts in posts.json. Exit.")
        return 0

    state = load_json(state_file, default={"next_index": 0, "history": []})
    if not isinstance(state, dict):
        state = {"next_index": 0, "history": []}

    pick = pick_next_post(posts, state)
    if not pick:
        print("All posts already published (next_index >= len(posts)). Exit.")
        return 0

    idx = pick["index"]
    item: PostItem = pick["post"]
    print(f"Posting index={idx} image_url={item.image_url}")

    result = post_photo(page_id, page_token, item)
    # result มักมี id และ post_id
    print("Posted OK:", json.dumps(result, ensure_ascii=False))

    # update state
    history = state.get("history")
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "index": idx,
            "ts": int(time.time()),
            "post_id": result.get("post_id"),
            "photo_id": result.get("id"),
            "image_url": item.image_url,
        }
    )
    state["history"] = history
    state["next_index"] = idx + 1

    save_json(state_file, state)
    print(f"State saved -> {state_file}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("ERROR:", str(e), file=sys.stderr)
        returncode = 1
        raise SystemExit(returncode)
