import os
import csv
import json
import random
import requests

from ai_engine import choose_product, generate_caption
from product_filter import filter_products, score_title

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")
AFF_ID = os.getenv("SHOPEE_AFFILIATE_ID")

STATE_FILE = "state.json"
HTTP_TIMEOUT = 20
MAX_ROWS = 2000


def log(msg):
    print(msg, flush=True)


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "posted" not in data or not isinstance(data["posted"], list):
                data["posted"] = []
            return data
    except Exception:
        return {"posted": []}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def clean_link(url):
    if not url:
        return ""
    return url.split("?")[0].strip()


def aff_link(url):
    base = clean_link(url)
    return f"{base}?affiliate_id={AFF_ID}" if AFF_ID else base


def read_csv():
    log("STEP 1: download csv")
    r = requests.get(CSV_URL, timeout=HTTP_TIMEOUT, stream=True)
    r.raise_for_status()

    lines = (
        line.decode("utf-8-sig", errors="ignore")
        for line in r.iter_lines()
        if line
    )

    reader = csv.DictReader(lines)
    rows = []

    for i, row in enumerate(reader):
        rows.append(row)
        if i >= MAX_ROWS:
            break

    random.shuffle(rows)
    log(f"STEP 2: csv rows loaded = {len(rows)}")
    return rows


def build_fallback_product(rows, state):
    posted = set(state.get("posted", []))

    # เลือกตัวที่ใกล้หมวดมากที่สุดก่อน
    candidates = []

    for r in rows:
        title = (r.get("title") or "").strip()
        link = (r.get("product_link") or "").strip()
        image = (r.get("image_link") or "").strip()

        if not title or not link or not image:
            continue

        if link in posted:
            continue

        candidates.append((score_title(title), {
            "name": title,
            "link": link,
            "image": image,
            "price": r.get("sale_price") or r.get("price") or "",
            "rating": r.get("item_rating") or "0",
            "sold": r.get("item_sold") or "0",
        }))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def fallback_caption(product, link):
    return f"""⚡ แนะนำจาก BEN Home & Electrical

{product['name']}

⭐ รีวิว {product['rating']}
🔥 ขายแล้ว {product['sold']}
💰 ราคา {product['price']} บาท

🛒 สั่งซื้อ
{link}

#BENHomeElectrical #ShopeeAffiliate"""


def build_caption(product):
    link = aff_link(product["link"])

    log("STEP 5: generate ai caption")
    caption = generate_caption(product)

    if caption:
        if link not in caption:
            caption = f"{caption}\n\n🛒 สั่งซื้อ\n{link}"
        return caption

    log("STEP 6: fallback caption")
    return fallback_caption(product, link)


def upload_photo(url):
    log("STEP 7: upload photo")
    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    r = requests.post(
        endpoint,
        data={
            "url": url,
            "published": "false",
            "access_token": TOKEN,
        },
        timeout=HTTP_TIMEOUT,
    )

    data = r.json()
    log(f"upload response: {data}")

    if "id" not in data:
        raise RuntimeError(data)

    return data["id"]


def post_image(media, text):
    log("STEP 8: create post")
    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    r = requests.post(
        endpoint,
        data={
            "message": text,
            "attached_media[0]": json.dumps({"media_fbid": media}),
            "access_token": TOKEN,
        },
        timeout=HTTP_TIMEOUT,
    )

    data = r.json()
    log(f"post response: {data}")
    return data


def comment_link(post_id, link):
    log("STEP 9: comment link")
    endpoint = f"https://graph.facebook.com/v25.0/{post_id}/comments"

    r = requests.post(
        endpoint,
        data={
            "message": f"🛒 ลิงก์สั่งซื้อ\n{link}",
            "access_token": TOKEN,
        },
        timeout=HTTP_TIMEOUT,
    )

    log(f"comment response: {r.json()}")


def main():
    if not PAGE_ID:
        raise ValueError("Missing PAGE_ID")
    if not TOKEN:
        raise ValueError("Missing PAGE_ACCESS_TOKEN")
    if not CSV_URL:
        raise ValueError("Missing SHOPEE_CSV_URL")

    state = load_state()
    rows = read_csv()

    log("STEP 3: filter products")
    products = filter_products(rows, state)
    log(f"STEP 4: valid products = {len(products)}")

    if products:
        product = choose_product(products)
        log(f"CHOSEN BY AI: {product['name']}")
    else:
        log("NO PRODUCT - fallback nearest category")
        product = build_fallback_product(rows, state)

        if not product:
            log("FALLBACK FAILED")
            return

        log(f"CHOSEN BY FALLBACK: {product['name']}")

    caption = build_caption(product)

    media = upload_photo(product["image"])
    res = post_image(media, caption)

    if "id" in res:
        comment_link(res["id"], aff_link(product["link"]))
        state["posted"].append(product["link"])
        save_state(state)
        log("POST SUCCESS")
    else:
        log("POST FAILED")


if __name__ == "__main__":
    main()
