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

HOT_CATEGORIES = {
    "lighting": [
        "electrical", "electric", "lighting", "light", "led", "lamp",
        "solar", "solar light", "โซล่า", "โซลาร์เซลล์",
        "หลอดไฟ", "โคมไฟ", "ไฟ", "ไฟ led"
    ],
    "power": [
        "plug", "socket", "power strip", "extension", "adapter",
        "charger", "usb charger", "cable", "wire", "battery",
        "ปลั๊ก", "ปลั๊กไฟ", "สายไฟ", "สายชาร์จ", "อุปกรณ์ไฟฟ้า",
        "เครื่องใช้ไฟฟ้า", "เบรกเกอร์", "สวิตช์", "switch", "breaker"
    ],
    "tools": [
        "tool", "tools", "hardware", "tester", "multimeter", "drill",
        "screwdriver", "plier", "wrench",
        "เครื่องมือ", "เครื่องมือช่าง", "ไขควง", "สว่าน", "คีม", "ประแจ", "มิเตอร์"
    ],
}

BLOCK_KEYWORDS = [
    "automotive", "auto", "car", "motorcycle", "bike", "brake", "steering",
    "ยานยนต์", "รถ", "รถยนต์", "มอเตอร์ไซค์", "อะไหล่รถ", "แต่งรถ",
    "fashion", "beauty", "cosmetic", "perfume", "makeup", "supplement",
    "แฟชั่น", "เครื่องสำอาง", "อาหารเสริม",
    "toy", "pet", "baby", "ของเล่น", "สัตว์เลี้ยง", "เด็กอ่อน"
]


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
        s = str(v).replace(",", "").strip()
        if not s:
            return 0
        return float(s)
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


def get_best_price(row):
    candidate_keys = [
        "sale_price",
        "discount_price",
        "final_price",
        "current_price",
        "promo_price",
        "price_min",
        "price",
    ]
    values = []
    for key in candidate_keys:
        v = parse_float(row.get(key))
        if v > 0:
            values.append(v)
    return min(values) if values else 0


def get_search_text(row, name):
    cat1 = (row.get("global_category1") or "").strip().lower()
    cat2 = (row.get("global_category2") or "").strip().lower()
    cat3 = (row.get("global_category3") or "").strip().lower()
    shop_name = (row.get("shop_name") or "").strip().lower()
    seller_name = (row.get("seller_name") or "").strip().lower()
    return f"{name} {cat1} {cat2} {cat3} {shop_name} {seller_name}".lower()


def detect_hot_category(row, name):
    text = get_search_text(row, name)

    if any(k in text for k in BLOCK_KEYWORDS):
        return None

    scores = {}
    for category, keywords in HOT_CATEGORIES.items():
        hits = sum(1 for k in keywords if k in text)
        scores[category] = hits

    best_category = max(scores, key=scores.get)
    if scores[best_category] <= 0:
        return None

    return best_category


def product_score(price, rating, sold, category):
    category_bonus = {
        "lighting": 30,
        "power": 25,
        "tools": 20,
    }.get(category, 0)

    if 79 <= price <= 499:
        price_score = 3
    elif 500 <= price <= 999:
        price_score = 2
    else:
        price_score = 1

    return category_bonus + rating * 5 + min(sold, 500) / 50 + price_score


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
        if len(lines) > 20000:
            break

    text = "\n".join(lines)
    reader = csv.DictReader(io.StringIO(text))

    products = []

    for row in reader:
        name = (row.get("title") or "").strip()
        link = (row.get("product_short link") or "").strip()
        image = (
            row.get("image_link")
            or row.get("additional_image_link")
            or ""
        ).strip()

        price = get_best_price(row)
        rating = parse_float(row.get("item_rating") or 0)
        sold = parse_float(row.get("item_sold") or 0)

        if not name or not link or not image:
            continue
        if rating < 4.2:
            continue
        if sold < 10:
            continue
        if price < 50 or price > 3000:
            continue

        hot_category = detect_hot_category(row, name)
        if not hot_category:
            continue

        score = product_score(price, rating, sold, hot_category)

        products.append({
            "name": name,
            "link": link,
            "image": image,
            "price": price,
            "rating": rating,
            "sold": sold,
            "hot_category": hot_category,
            "score": score
        })

    products.sort(key=lambda x: x["score"], reverse=True)
    products = products[:500]

    print("CSV PRODUCTS:", len(products), flush=True)
    return products


def ai_caption(product):
    price_text = format_price(product["price"])

    hashtags = {
        "lighting": "#BENHomeElectrical #ไฟLED #โคมไฟ #ของใช้ในบ้าน",
        "power": "#BENHomeElectrical #อุปกรณ์ไฟฟ้า #ปลั๊กไฟ #ของใช้ในบ้าน",
        "tools": "#BENHomeElectrical #เครื่องมือช่าง #อุปกรณ์ไฟฟ้า #ของใช้ในบ้าน",
    }

    fallback_options = {
        "lighting": f"""🔥 ของใช้ไฟฟ้าน่าใช้สำหรับบ้าน

{product['name']}

💰 ราคา {price_text}

เหมาะกับงานแสงสว่างและใช้งานในบ้าน
กดดูสินค้าได้ที่ลิงก์ด้านล่าง 👇

{hashtags['lighting']}""",
        "power": f"""⚡ ไอเทมน่าใช้สำหรับบ้านและงานไฟฟ้า

{product['name']}

💰 ราคา {price_text}

ใช้งานง่าย น่ามีติดบ้านไว้
ดูรายละเอียดได้ที่ลิงก์ด้านล่าง 👇

{hashtags['power']}""",
        "tools": f"""🛠 ของน่าใช้สำหรับบ้านและงานช่าง

{product['name']}

💰 ราคา {price_text}

ใครกำลังหาอุปกรณ์ดี ๆ ลองดูตัวนี้ได้เลย 👇

{hashtags['tools']}"""
    }

    fallback = fallback_options.get(product["hot_category"], fallback_options["power"])

    if not OPENAI_KEY:
        return fallback

    prompt = f"""
เขียนโพสต์ Facebook ภาษาไทย สำหรับเพจ BEN Home & Electrical

สินค้า: {product['name']}
ราคา: {price_text}
หมวดหลัก: {product['hot_category']}

เงื่อนไข:
- สั้น
- อ่านง่าย
- น่าซื้อ
- แนวแนะนำสินค้าใช้งานจริง
- ใส่ราคาได้
- ห้ามพูดถึงยอดขาย
- ห้ามบอกว่าขายได้กี่ชิ้น
- ห้ามใส่ hashtag ShopeeAffiliate
- ห้ามใส่ลิงก์ในคำตอบ
- เน้นให้ตรงกับหมวด {product['hot_category']}
- ใส่ hashtag 3-4 อันที่เกี่ยวกับเพจ
""".strip()

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

    lighting = [p for p in products if p["hot_category"] == "lighting" and p["link"] not in posted]
    power = [p for p in products if p["hot_category"] == "power" and p["link"] not in posted]
    tools = [p for p in products if p["hot_category"] == "tools" and p["link"] not in posted]

    buckets = [b for b in [lighting[:15], power[:15], tools[:15]] if b]

    if not buckets:
        print("NO NEW PRODUCT", flush=True)
        return None

    chosen_bucket = random.choice(buckets)
    return random.choice(chosen_bucket)


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
