import os
import csv
import io
import json
import random
import requests
from datetime import datetime, timedelta, timezone

PAGE_ID = os.environ["PAGE_ID"]
PAGE_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]
CSV_URL = os.environ["SHOPEE_CSV_URL"]
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

POST_DB = "posted_products.json"
LOG_FILE = "post_log.json"

TH_TZ = timezone(timedelta(hours=7))


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def parse_float(v):
    try:
        return float(str(v).replace(",", ""))
    except:
        return 0


def format_price(v):
    try:
        return f"{float(v):,.0f} บาท"
    except:
        return ""


def log_post(product, post_id):

    logs = load_json(LOG_FILE, [])

    logs.append({
        "time": str(datetime.now(TH_TZ)),
        "name": product["name"],
        "price": product["price"],
        "link": product["link"],
        "post_id": post_id
    })

    save_json(LOG_FILE, logs)


# ======================
# LOAD CSV (100k rows)
# ======================

def load_csv_products():

    print("STEP: load csv")

    r = requests.get(CSV_URL, stream=True, timeout=120)
    r.raise_for_status()

    reader = csv.DictReader(
        (line.decode("utf-8", errors="ignore") for line in r.iter_lines() if line)
    )

    products = []
    scanned = 0

    for row in reader:

        scanned += 1

        if scanned > 100000:
            break

        name = (row.get("title") or "").strip()

        link = (
            row.get("product_short link")
            or row.get("product_link")
            or ""
        ).strip()

        image = (
            row.get("image_link")
            or ""
        ).strip()

        price = parse_float(row.get("price"))
        rating = parse_float(row.get("item_rating"))
        sold = parse_float(row.get("item_sold"))

        if not name or not link or not image:
            continue

        if rating < 4:
            continue

        if sold < 10:
            continue

        products.append({
            "name": name,
            "link": link,
            "image": image,
            "price": price,
            "rating": rating,
            "sold": sold
        })

        if len(products) >= 500:
            break

    print("CSV SCANNED:", scanned)
    print("CSV PRODUCTS:", len(products))

    return products


# ======================
# PICK BEST PRODUCT
# ======================

def pick_product(products):

    posted = load_json(POST_DB, [])

    candidates = [p for p in products if p["link"] not in posted]

    if not candidates:
        print("NO NEW PRODUCT")
        return None

    candidates.sort(
        key=lambda x: (x["rating"], x["sold"], x["price"]),
        reverse=True
    )

    top = candidates[:50]

    return random.choice(top)


# ======================
# AI CAPTION
# ======================

def ai_caption(product):

    price = format_price(product["price"])

    fallback = f"""🔥 {product['name']}

💰 ราคา {price}

ของน่าใช้สำหรับบ้านและงานไฟฟ้า
ดูสินค้าได้ที่ลิงก์ด้านล่าง 👇"""

    if not OPENAI_KEY:
        return fallback

    prompt = f"""
เขียนโพสต์ Facebook ภาษาไทย

สินค้า: {product['name']}
ราคา: {price}

เงื่อนไข
- อ่านง่าย
- สั้น
- น่าซื้อ
- ห้ามพูดยอดขาย
"""

    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": prompt}]
    }

    try:

        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=20
        )

        return r.json()["choices"][0]["message"]["content"]

    except Exception as e:

        print("OPENAI ERROR:", e)

        return fallback


# ======================
# FACEBOOK POST
# ======================

def post_facebook(product):

    caption = ai_caption(product)

    caption = f"""{caption}

🛒 สั่งซื้อสินค้า
{product['link']}"""

    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    payload = {
        "url": product["image"],
        "caption": caption,
        "access_token": PAGE_TOKEN
    }

    print("STEP: facebook post")

    r = requests.post(url, data=payload)

    data = r.json()

    print("POST RESPONSE:", data)

    return data


# ======================
# COMMENT LINK
# ======================

def comment_link(post_id, link):

    print("STEP: comment affiliate")

    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"

    payload = {
        "message": f"🛒 สั่งซื้อสินค้า\n{link}",
        "access_token": PAGE_TOKEN
    }

    r = requests.post(url, data=payload)

    print("COMMENT:", r.text)


# ======================
# RUN BOT
# ======================

def run():

    products = load_csv_products()

    if not products:
        print("NO PRODUCTS")
        return

    product = pick_product(products)

    if not product:
        return

    res = post_facebook(product)

    post_id = res.get("post_id") or res.get("id")

    if not post_id:
        print("POST FAIL")
        return

    comment_link(post_id, product["link"])

    posted = load_json(POST_DB, [])
    posted.append(product["link"])
    save_json(POST_DB, posted)

    log_post(product, post_id)

    print("POST SUCCESS")


if __name__ == "__main__":
    run()
