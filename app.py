import os
import json
import random
import requests

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

STATE_FILE = "state.json"
POSTED_PRODUCTS_FILE = "posted_products.json"
REELS_CANDIDATES_FILE = "reels_candidates.json"
TOP_PRODUCTS_FILE = "top_products.json"

HTTP_TIMEOUT = 20
TOP_POOL = 30
REELS_POOL = 50

CAPTIONS = [
    """⚡ แนะนำจาก BEN Home & Electrical

{name}

⭐ รีวิว {rating}
🔥 ขายแล้ว {sold}
💰 ราคา {price} บาท

🛒 กดดูสินค้า
{link}

#BENHomeElectrical #Shopee #อุปกรณ์ไฟฟ้า""",

    """🔥 สินค้าขายดี

{name}

⭐ {rating}
📦 ขายแล้ว {sold}
💰 {price} บาท

👉 {link}

#BENHomeElectrical #ของใช้ในบ้าน""",

    """🏠 ของมันต้องมีติดบ้าน

{name}

⭐ รีวิว {rating}
🔥 ยอดขาย {sold}
💰 ราคา {price}

🛒 สั่งซื้อ
{link}

#BENHomeElectrical"""
]


def log(msg):
    print(msg, flush=True)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_state():
    state = load_json(STATE_FILE, {"posted": []})
    if "posted" not in state:
        state["posted"] = state.get("posted_links", [])
    if not isinstance(state["posted"], list):
        state["posted"] = []
    return state


def save_state(state):
    state["posted"] = state["posted"][-1000:]
    save_json(STATE_FILE, state)


def load_products():
    data = load_json(TOP_PRODUCTS_FILE, [])
    if not isinstance(data, list):
        return []
    return data


def append_posted_product(p):
    data = load_json(POSTED_PRODUCTS_FILE, [])

    data.append({
        "title": p["title"],
        "product_link": p["product_link"],
        "image_link": p.get("image_link"),
        "rating": p.get("rating"),
        "sold": p.get("sold"),
        "price": p.get("price"),
        "score": p.get("score")
    })

    data = data[-1000:]
    save_json(POSTED_PRODUCTS_FILE, data)


def refresh_reels_candidates(products, state):
    posted = set(state["posted"])

    ranked = sorted(
        [
            p for p in products
            if (p.get("product_link") or "").strip()
            and (p.get("image_link") or "").strip()
            and (p.get("product_link") not in posted)
        ],
        key=lambda x: float(x.get("score", 0) or 0),
        reverse=True
    )

    reels = []
    for p in ranked[:REELS_POOL]:
        reels.append({
            "title": p.get("title"),
            "product_link": p.get("product_link"),
            "image_link": p.get("image_link"),
            "rating": p.get("rating"),
            "sold": p.get("sold"),
            "price": p.get("price"),
            "score": p.get("score")
        })

    save_json(REELS_CANDIDATES_FILE, reels)
    log(f"reels candidates = {len(reels)}")


def build_pool(products, state):
    posted = set(state["posted"])
    pool = []

    for p in products:
        link = (p.get("product_link") or "").strip()
        img = (p.get("image_link") or "").strip()
        title = (p.get("title") or "").strip()

        if not link or not img or not title:
            continue

        if link in posted:
            continue

        pool.append(p)

    log(f"valid products = {len(pool)}")
    return pool


def choose_product(pool):
    if not pool:
        return None

    ranked = sorted(pool, key=lambda x: float(x.get("score", 0) or 0), reverse=True)
    top = ranked[:TOP_POOL]

    log("TOP CANDIDATES:")
    for i, p in enumerate(top[:5], start=1):
        log(
            f"{i}. sold={p.get('sold')} rating={p.get('rating')} "
            f"price={p.get('price')} score={p.get('score')} "
            f"title={str(p.get('title', ''))[:80]}"
        )

    return random.choice(top)


def caption(p):
    c = random.choice(CAPTIONS)
    return c.format(
        name=p["title"],
        rating=p.get("rating", ""),
        sold=p.get("sold", ""),
        price=p.get("price", ""),
        link=p["product_link"]
    )


def upload(img):
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"
    r = requests.post(
        url,
        data={
            "url": img,
            "published": "false",
            "access_token": TOKEN
        },
        timeout=HTTP_TIMEOUT
    ).json()

    if "id" not in r:
        raise RuntimeError(r)

    return r["id"]


def post_product(p):
    log("STEP 1: upload image")
    media = upload(p["image_link"])

    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    payload = {
        "message": caption(p),
        "attached_media[0]": json.dumps({"media_fbid": media}),
        "access_token": TOKEN
    }

    log("STEP 2: create post")
    r = requests.post(url, data=payload, timeout=HTTP_TIMEOUT).json()
    return r


def comment_link(post_id, link):
    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"
    payload = {
        "message": f"🛒 ลิงก์สินค้า\n{link}",
        "access_token": TOKEN
    }
    r = requests.post(url, data=payload, timeout=HTTP_TIMEOUT).json()
    return r


def main():
    state = load_state()
    products = load_products()

    if not products:
        log("no top products")
        return

    refresh_reels_candidates(products, state)

    pool = build_pool(products, state)
    if not pool:
        log("no product")
        return

    p = choose_product(pool)
    if not p:
        log("no chosen product")
        return

    log(
        f"CHOSEN sold={p.get('sold')} rating={p.get('rating')} "
        f"price={p.get('price')} score={p.get('score')}"
    )

    res = post_product(p)
    log(res)

    if "id" in res:
        comment_res = comment_link(res["id"], p["product_link"])
        log(comment_res)

        state["posted"].append(p["product_link"])
        save_state(state)
        append_posted_product(p)

        log("done")


if __name__ == "__main__":
    main()
