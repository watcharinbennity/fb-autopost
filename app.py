import os
import csv
import io
import json
import random
import requests
from datetime import datetime

PAGE_ID = os.environ["PAGE_ID"]
PAGE_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]
CSV_URL = os.environ["SHOPEE_CSV_URL"]
AFF_ID = os.environ["SHOPEE_AFFILIATE_ID"]
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

POST_DB = "posted.json"


def load_posted():
    if os.path.exists(POST_DB):
        return json.load(open(POST_DB))
    return []


def save_posted(data):
    json.dump(data, open(POST_DB, "w"))


def parse_float(v):
    try:
        return float(v)
    except:
        return 0


def load_csv_products():

    print("STEP: load csv", flush=True)

    r = requests.get(CSV_URL, timeout=60)
    r.raise_for_status()

    text = r.content.decode("utf-8", errors="ignore")

    reader = csv.DictReader(io.StringIO(text))

    products = []

    for row in reader:

        if len(products) > 500:
            break

        name = row.get("product_name", "").strip()

        link = (
            row.get("offer_link")
            or row.get("product_link")
            or ""
        ).strip()

        image = (
            row.get("image_url")
            or row.get("image")
            or ""
        ).strip()

        price = parse_float(
            row.get("price_min")
            or row.get("price")
            or 0
        )

        rating = parse_float(
            row.get("rating_star")
            or 0
        )

        if not name or not link or not image:
            continue

        if rating < 4:
            continue

        products.append({
            "name": name,
            "link": link,
            "image": image,
            "price": price,
            "rating": rating
        })

    print("CSV PRODUCTS:", len(products), flush=True)

    return products


def ai_caption(product):

    if not OPENAI_KEY:
        return f"""🔥 {product['name']}

💰 ราคา {int(product['price'])} บาท

สินค้าขายดีจาก Shopee
ของแท้ คุณภาพดี ใช้งานคุ้มค่า

🛒 กดดูสินค้าในคอมเมนต์ 👇"""

    prompt = f"""
เขียนโพสต์ขายของ Facebook ภาษาไทย
สินค้า: {product['name']}
ราคา: {product['price']} บาท
ไม่ต้องพูดยอดขาย
เน้นให้คนอยากซื้อ
"""

    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": prompt}]
    }

    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=data,
        timeout=60
    )

    try:
        return r.json()["choices"][0]["message"]["content"]
    except:
        return f"{product['name']}\nราคา {product['price']} บาท\nดูสินค้าในคอมเมนต์"


def post_facebook(product, caption):

    print("STEP: facebook post", flush=True)

    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    payload = {
        "url": product["image"],
        "caption": caption,
        "access_token": PAGE_TOKEN
    }

    r = requests.post(url, data=payload)

    return r.json()


def comment_link(post_id, link):

    print("STEP: comment affiliate", flush=True)

    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"

    payload = {
        "message": f"🛒 สั่งซื้อสินค้า\n{link}",
        "access_token": PAGE_TOKEN
    }

    requests.post(url, data=payload)


def pick_product(products):

    posted = load_posted()

    candidates = [
        p for p in products
        if p["link"] not in posted
    ]

    if not candidates:
        print("NO NEW PRODUCT")
        return None

    return random.choice(candidates)


def run():

    products = load_csv_products()

    if not products:
        print("NO PRODUCTS")
        return

    product = pick_product(products)

    if not product:
        return

    caption = ai_caption(product)

    res = post_facebook(product, caption)

    post_id = res.get("post_id") or res.get("id")

    if not post_id:
        print("POST FAIL", res)
        return

    comment_link(post_id, product["link"])

    posted = load_posted()
    posted.append(product["link"])
    save_posted(posted)

    print("POST SUCCESS")


if __name__ == "__main__":
    run()
