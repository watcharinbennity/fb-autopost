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

POSTED_FILE = "posted_products.json"
LOG_FILE = "post_log.json"

TH_TZ = timezone(timedelta(hours=7))


def load_json(path, default=None):
    if default is None:
        default = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_posted(raw):
    cleaned = []
    if not isinstance(raw, list):
        return cleaned

    for item in raw:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip())
        elif isinstance(item, dict):
            link = item.get("link")
            if isinstance(link, str) and link.strip():
                cleaned.append(link.strip())

    return list(dict.fromkeys(cleaned))


def log_post(post_type, product=None, post_id=None):
    logs = load_json(LOG_FILE, [])
    if not isinstance(logs, list):
        logs = []

    row = {
        "time": str(datetime.now(TH_TZ)),
        "type": post_type,
        "post_id": post_id or ""
    }

    if isinstance(product, dict):
        row.update({
            "name": product.get("name", ""),
            "price": product.get("price", 0),
            "rating": product.get("rating", 0),
            "link": product.get("link", "")
        })

    logs.append(row)
    save_json(LOG_FILE, logs)


def parse_float(v, default=0.0):
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).replace(",", ""))
    except Exception:
        return default


def parse_int(v, default=0):
    try:
        if v is None or str(v).strip() == "":
            return default
        return int(float(str(v).replace(",", "")))
    except Exception:
        return default


def format_price(v):
    try:
        p = float(v)
        if p <= 0:
            return ""
        return f"{p:,.0f} บาท"
    except Exception:
        return ""


def is_relevant_product(row, name):
    # ใช้หมวดจริงจากไฟล์ตัวอย่าง
    c1 = (row.get("global_category1") or "").strip().lower()
    c2 = (row.get("global_category2") or "").strip().lower()
    c3 = (row.get("global_category3") or "").strip().lower()
    text = f"{c1} {c2} {c3} {name.lower()}"

    allow_keywords = [
        "home", "living", "tools", "accessories", "charger", "chargers",
        "cable", "cables", "lighting", "electrical", "led", "plug",
        "solar", "lamp", "light", "socket", "adapter", "power",
        "drill", "screwdriver", "plier", "wrench", "tool", "เครื่องมือ",
        "ไฟ", "ปลั๊ก", "โคม", "สายไฟ", "ไฟฟ้า", "หลอด", "ชาร์จ"
    ]

    return any(k in text for k in allow_keywords)


def load_csv_products(max_scan_rows=100000, max_candidates=500):
    print("STEP: load csv", flush=True)

    try:
        r = requests.get(CSV_URL, stream=True, timeout=(15, 60))
        r.raise_for_status()

        decoded_lines = (
            line.decode("utf-8", errors="ignore")
            for line in r.iter_lines()
            if line
        )

        reader = csv.DictReader(decoded_lines)
        print("CSV HEADERS:", reader.fieldnames, flush=True)

        products = []
        scanned = 0

        for row in reader:
            scanned += 1
            if scanned > max_scan_rows:
                break

            # ใช้หัวคอลัมน์จริงจากไฟล์ตัวอย่างของคุณ
            name = (row.get("title") or "").strip()

            link = (
                row.get("product_short link")
                or row.get("product_link")
                or ""
            ).strip()

            image = (
                row.get("image_link")
                or row.get("additional_image_link")
                or ""
            ).strip()

            price = parse_float(row.get("price") or 0)
            rating = parse_float(row.get("item_rating") or 0)
            sold = parse_int(row.get("item_sold") or 0)
            stock = parse_int(row.get("stock") or 0)

            if not name or not link or not image:
                continue

            if stock <= 0:
                continue

            if rating < 4:
                continue

            if sold < 10:
                continue

            if not is_relevant_product(row, name):
                continue

            products.append({
                "name": name,
                "link": link,
                "image": image,
                "price": price,
                "rating": rating,
                "sold": sold
            })

            if len(products) >= max_candidates:
                break

        print(f"CSV SCANNED: {scanned}", flush=True)
        print(f"CSV PRODUCTS: {len(products)}", flush=True)
        return products

    except requests.exceptions.Timeout:
        print("CSV TIMEOUT", flush=True)
        return []
    except Exception as e:
        print("CSV ERROR:", e, flush=True)
        return []


def ai_caption(product):
    price_text = format_price(product.get("price", 0))

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
- น่าคลิก
- ใส่ราคาได้
- ห้ามพูดถึงยอดขาย
- ห้ามบอกว่าขายได้กี่ชิ้น
- โทนเหมือนแนะนำของใช้ไฟฟ้า ของใช้ในบ้าน หรือเครื่องมือช่าง
- ปิดท้ายชวนกดดูสินค้า
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

    try:
        data = r.json()
    except Exception:
        print("POST RAW:", r.text, flush=True)
        return {}

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
    posted = set(normalize_posted(load_json(POSTED_FILE, [])))

    candidates = [p for p in products if p["link"] not in posted]

    if not candidates:
        print("NO NEW PRODUCT", flush=True)
        return None

    # ให้สินค้าที่คะแนนสูง / ยอดดี / ราคาไม่แปลก มีสิทธิ์มากขึ้น
    candidates.sort(
        key=lambda x: (
            parse_float(x.get("rating", 0)),
            parse_int(x.get("sold", 0)),
            parse_float(x.get("price", 0))
        ),
        reverse=True
    )

    pool = candidates[:50] if len(candidates) >= 50 else candidates
    return random.choice(pool)


def save_posted_link(link):
    posted = normalize_posted(load_json(POSTED_FILE, []))
    posted.append(link)
    save_json(POSTED_FILE, list(dict.fromkeys(posted)))


def run():
    products = load_csv_products(max_scan_rows=100000, max_candidates=500)

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
    save_posted_link(product["link"])
    log_post("product", product=product, post_id=post_id)

    print("POST SUCCESS", flush=True)


if __name__ == "__main__":
    run()
