import os
import csv
import io
import json
import random
import requests

PAGE_ID = os.environ["PAGE_ID"]
PAGE_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]
CSV_URL = os.environ["SHOPEE_CSV_URL"]
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

POST_DB = "posted.json"


def load_posted():
    if os.path.exists(POST_DB):
        with open(POST_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_posted(data):
    with open(POST_DB, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_float(v):
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return 0


def format_price(v):
    try:
        p = float(v)
        if p <= 0:
            return ""
        return f"{p:,.0f} บาท"
    except Exception:
        return ""


def load_csv_products():
    print("STEP: load csv", flush=True)

    r = requests.get(CSV_URL, stream=True, timeout=60)
    r.raise_for_status()

    lines = []

    for line in r.iter_lines():
        if not line:
            continue

        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="ignore")

        lines.append(line)

        # อ่านแค่ช่วงต้นของไฟล์พอ
        if len(lines) > 1000:
            break

    text = "\n".join(lines)
    reader = csv.DictReader(io.StringIO(text))

    products = []

    for row in reader:
        name = (row.get("title") or "").strip()

        # ใช้ short link ก่อนเสมอ
        link = (
            row.get("product_short link")
            or ""
        ).strip()

        image = (
            row.get("image_link")
            or row.get("additional_image_link")
            or ""
        ).strip()

        price = parse_float(row.get("price") or 0)
        rating = parse_float(row.get("item_rating") or 0)
        sold = parse_float(row.get("item_sold") or 0)

        if not name:
            continue
        if not link:
            continue
        if not image:
            continue

        # AI v3 filter
        if rating < 4.5:
            continue

        if sold < 50:
            continue

        if price < 50 or price > 1500:
            continue

        products.append({
            "name": name,
            "link": link,
            "image": image,
            "price": price,
        })

        if len(products) >= 500:
            break

    print("CSV PRODUCTS:", len(products), flush=True)
    return products


def ai_caption(product):
    price_text = format_price(product["price"])

    fallback = f"""🔥 ของใช้ในบ้านที่กำลังฮิต

{product['name']}

💰 ราคา {price_text}

เหมาะกับบ้าน งานช่าง งานไฟฟ้า
ใช้งานง่าย ประหยัดพื้นที่

กดดูสินค้า / โค้ดส่วนลดได้ที่ลิงก์ด้านล่าง 👇

#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #ShopeeAffiliate"""

    if not OPENAI_KEY:
        return fallback

    prompt = f"""
เขียนโพสต์ขายของ Facebook ภาษาไทย สำหรับเพจ BEN Home & Electrical

สินค้า: {product['name']}
ราคา: {price_text}

เงื่อนไข:
- สั้น
- อ่านง่าย
- น่าซื้อ
- แนวรีวิวสินค้า
- ใส่ราคาได้
- ห้ามพูดถึงยอดขาย
- ห้ามบอกว่าขายได้กี่ชิ้น
""".strip()

    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "gpt-4.1-mini",
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=20
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print("OPENAI ERROR:", e, flush=True)
        return fallback


def build_caption(product):
    base = ai_caption(product).strip()

    return f"""{base}

🛒 สั่งซื้อสินค้า
{product['link']}"""


def post_facebook(product, caption):
    print("STEP: facebook post", flush=True)

    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    payload = {
        "url": product["image"],
        "caption": caption,
        "access_token": PAGE_TOKEN
    }

    r = requests.post(url, data=payload, timeout=30)
    data = r.json()

    print("POST RESPONSE:", data, flush=True)
    return data


def comment_link(post_id, link):
    print("STEP: comment affiliate", flush=True)

    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"

    payload = {
        "message": f"🛒 สั่งซื้อสินค้า\n{link}",
        "access_token": PAGE_TOKEN
    }

    try:
        r = requests.post(url, data=payload, timeout=20)
        print("COMMENT:", r.text, flush=True)
    except Exception as e:
        print("COMMENT ERROR:", e, flush=True)


def pick_product(products):
    posted = load_posted()

    candidates = [
        p for p in products
        if p["link"] not in posted
    ]

    if not candidates:
        print("NO NEW PRODUCT", flush=True)
        return None

    return random.choice(candidates)


def run():
    products = load_csv_products()

    if not products:
        print("NO PRODUCTS", flush=True)
        return

    product = pick_product(products)

    if not product:
        return

    caption = build_caption(product)
    res = post_facebook(product, caption)

    post_id = res.get("post_id") or res.get("id")

    if not post_id:
        print("POST FAIL", res, flush=True)
        return

    comment_link(post_id, product["link"])

    posted = load_posted()
    posted.append(product["link"])
    save_posted(posted)

    print("POST SUCCESS", flush=True)


if __name__ == "__main__":
    run()
