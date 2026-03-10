import os
import csv
import json
import random
import requests

PAGE_ID = os.environ["PAGE_ID"]
PAGE_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]
CSV_URL = os.environ["SHOPEE_CSV_URL"]
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

POST_DB = "posted_products.json"

KEYWORDS = [
    "ไฟ", "led", "หลอด", "โคม", "solar", "โซล่า",
    "ปลั๊ก", "สายไฟ", "adapter", "charger", "battery",
    "สว่าน", "ไขควง", "คีม", "ประแจ", "tool", "tools",
    "electrical", "power", "socket", "switch", "เบรกเกอร์",
    "เครื่องมือ", "ช่าง", "lamp", "light"
]


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_float(v):
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return 0.0


def parse_int(v):
    try:
        return int(float(str(v).replace(",", "")))
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


def is_match(name, row):
    text = " ".join([
        (name or "").lower(),
        str(row.get("global_category1", "")).lower(),
        str(row.get("global_category2", "")).lower(),
        str(row.get("global_category3", "")).lower(),
    ])
    return any(k.lower() in text for k in KEYWORDS)


def load_csv_products():
    print("STEP: load csv", flush=True)

    r = requests.get(CSV_URL, stream=True, timeout=(20, 90))
    r.raise_for_status()

    reader = csv.DictReader(
        (line.decode("utf-8", errors="ignore") for line in r.iter_lines() if line)
    )

    products = []
    scanned = 0

    for row in reader:
        scanned += 1
        if scanned > 20000:
            break

        name = (row.get("title") or "").strip()
        link = (row.get("product_short link") or row.get("product_link") or "").strip()
        image = (row.get("image_link") or row.get("additional_image_link") or "").strip()
        price = parse_float(row.get("price"))
        rating = parse_float(row.get("item_rating"))
        sold = parse_int(row.get("item_sold"))
        stock = parse_int(row.get("stock"))

        if not name or not link or not image:
            continue
        if stock <= 0:
            continue
        if rating < 4:
            continue
        if sold < 10:
            continue
        if not is_match(name, row):
            continue

        products.append({
            "name": name,
            "link": link,
            "image": image,
            "price": price,
            "rating": rating,
            "sold": sold
        })

        if len(products) >= 300:
            break

    print("CSV SCANNED:", scanned, flush=True)
    print("CSV PRODUCTS:", len(products), flush=True)
    return products


def ai_caption(product):
    price_text = format_price(product["price"])

    fallback = f"""🔥 {product['name']}

💰 ราคา {price_text}

ของน่าใช้สำหรับบ้านและงานไฟฟ้า
ดูสินค้าได้ที่ลิงก์ด้านล่าง 👇"""

    if not OPENAI_KEY:
        return fallback

    prompt = f"""
เขียนโพสต์ Facebook ภาษาไทย สำหรับเพจ BEN Home & Electrical

สินค้า: {product['name']}
ราคา: {price_text}

เงื่อนไข:
- สั้น
- อ่านง่าย
- น่าซื้อ
- ใส่ราคาได้
- ห้ามพูดยอดขาย
- โทนเหมือนแนะนำของใช้ไฟฟ้าและเครื่องมือช่าง
""".strip()

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print("OPENAI ERROR:", e, flush=True)
        return fallback


def pick_product(products):
    posted = set(load_json(POST_DB, []))
    candidates = [p for p in products if p["link"] not in posted]

    if not candidates:
        print("NO NEW PRODUCT", flush=True)
        return None

    candidates.sort(key=lambda x: (x["rating"], x["sold"]), reverse=True)
    top = candidates[:40] if len(candidates) >= 40 else candidates
    return random.choice(top)


def post_facebook(product):
    caption = ai_caption(product).strip()
    caption = f"""{caption}

🛒 สั่งซื้อสินค้า
{product['link']}"""

    print("STEP: facebook post", flush=True)

    r = requests.post(
        f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos",
        data={
            "url": product["image"],
            "caption": caption,
            "access_token": PAGE_TOKEN
        },
        timeout=30
    )

    data = r.json()
    print("POST RESPONSE:", data, flush=True)
    return data


def comment_link(post_id, link):
    print("STEP: comment affiliate", flush=True)

    r = requests.post(
        f"https://graph.facebook.com/v25.0/{post_id}/comments",
        data={
            "message": f"🛒 สั่งซื้อสินค้า\n{link}",
            "access_token": PAGE_TOKEN
        },
        timeout=20
    )

    print("COMMENT:", r.text, flush=True)


def save_posted(link):
    posted = load_json(POST_DB, [])
    posted.append(link)
    save_json(POST_DB, list(dict.fromkeys(posted)))


def run():
    products = load_csv_products()
    if not products:
        print("NO PRODUCTS", flush=True)
        return

    product = pick_product(products)
    if not product:
        return

    res = post_facebook(product)
    post_id = res.get("post_id") or res.get("id")

    if not post_id:
        print("POST FAIL", res, flush=True)
        return

    comment_link(post_id, product["link"])
    save_posted(product["link"])
    print("POST SUCCESS", flush=True)


if __name__ == "__main__":
    run()
