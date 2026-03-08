import os
import csv
import io
import json
import random
import requests
from openai import OpenAI

PAGE_ID = os.environ["PAGE_ID"]
PAGE_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]
CSV_URL = os.environ["SHOPEE_CSV_URL"]
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

POST_DB = "posted.json"

HOT_CATEGORIES = {
    "lighting": [
        "led", "light", "lamp", "lighting", "solar", "solar light",
        "โซล่า", "โซลาร์เซลล์", "หลอดไฟ", "โคมไฟ", "ไฟ", "ไฟ led"
    ],
    "power": [
        "plug", "socket", "adapter", "charger", "usb charger", "power strip",
        "extension", "cable", "wire", "battery", "switch", "breaker",
        "ปลั๊ก", "ปลั๊กไฟ", "สายไฟ", "สายชาร์จ", "เบรกเกอร์", "สวิตช์",
        "อุปกรณ์ไฟฟ้า", "เครื่องใช้ไฟฟ้า"
    ],
    "tools": [
        "tool", "tools", "hardware", "tester", "multimeter", "drill",
        "screwdriver", "plier", "wrench",
        "เครื่องมือ", "เครื่องมือช่าง", "ไขควง", "สว่าน", "คีม", "ประแจ", "มิเตอร์",
        "เชื่อม", "หน้ากากเชื่อม", "welder", "welding"
    ],
}

BLOCK_KEYWORDS = [
    "car", "automotive", "motor", "bike", "brake", "steering",
    "รถ", "รถยนต์", "มอเตอร์ไซค์", "อะไหล่รถ", "แต่งรถ", "พวงมาลัย", "ผ้าเบรค",
    "fashion", "cosmetic", "beauty", "supplement",
    "เสื้อ", "กางเกง", "เครื่องสำอาง", "อาหารเสริม",
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
        s = str(v).replace(",", "").replace("฿", "").strip()
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


def get_price_candidates(row):
    candidate_keys = [
        "sale_price",
        "discount_price",
        "final_price",
        "current_price",
        "promo_price",
        "price_min",
        "price_max",
        "price",
    ]

    values = []
    for key in candidate_keys:
        v = parse_float(row.get(key))
        if v > 0:
            values.append(v)

    return sorted(set(values))


def get_price_info(row, name=""):
    values = get_price_candidates(row)

    if not values:
        return {
            "price": 0,
            "price_text": "",
            "is_range": False
        }

    low = min(values)
    high = max(values)

    variant_hint = False
    name_l = (name or "").lower()

    if "/" in name_l or "รุ่น" in name_l or "model" in name_l:
        variant_hint = True

    if high > low:
        variant_hint = True

    if variant_hint:
        return {
            "price": low,
            "price_text": f"เริ่มต้น {low:,.0f} บาท",
            "is_range": True
        }

    return {
        "price": low,
        "price_text": f"{low:,.0f} บาท",
        "is_range": False
    }


def get_search_text(row, name):
    cat1 = (row.get("global_category1") or "").strip().lower()
    cat2 = (row.get("global_category2") or "").strip().lower()
    cat3 = (row.get("global_category3") or "").strip().lower()
    shop_name = (row.get("shop_name") or "").strip().lower()
    seller_name = (row.get("seller_name") or "").strip().lower()
    return f"{name} {cat1} {cat2} {cat3} {shop_name} {seller_name}".lower()


def detect_hot_category(row, name):
    text = get_search_text(row, name)

    if any(b in text for b in BLOCK_KEYWORDS):
        return None

    scores = {}
    for cat, words in HOT_CATEGORIES.items():
        hits = sum(1 for w in words if w in text)
        scores[cat] = hits

    best = max(scores, key=scores.get)
    if scores[best] <= 0:
        return None

    return best


def score_product(price, rating, sold, category):
    category_bonus = {
        "lighting": 45,
        "power": 40,
        "tools": 42,
    }.get(category, 0)

    if 79 <= price <= 499:
        price_score = 4
    elif 500 <= price <= 999:
        price_score = 3
    elif 1000 <= price <= 2000:
        price_score = 2
    else:
        price_score = 1

    sold_score = min(sold, 500) / 40
    rating_score = rating * 6

    return category_bonus + price_score + sold_score + rating_score


def load_products():
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

        price_info = get_price_info(row, name)
        price = price_info["price"]
        price_text = price_info["price_text"]

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

        category = detect_hot_category(row, name)
        if not category:
            continue

        score = score_product(price, rating, sold, category)

        products.append({
            "name": name,
            "link": link,
            "image": image,
            "price": price,
            "price_text": price_text,
            "rating": rating,
            "sold": sold,
            "category": category,
            "score": score
        })

    products.sort(key=lambda x: x["score"], reverse=True)
    print("CSV PRODUCTS:", len(products), flush=True)
    return products[:500]


def fallback_caption(product):
    price_text = product.get("price_text") or format_price(product["price"])

    by_cat = {
        "lighting": f"""🔥 ของใช้ไฟฟ้าน่าใช้สำหรับบ้าน

{product['name']}

💰 ราคา {price_text}

เหมาะกับงานแสงสว่างและใช้งานในบ้าน
กดดูสินค้าได้ที่ลิงก์ด้านล่าง 👇

#BENHomeElectrical #ไฟLED #โคมไฟ #ของใช้ในบ้าน""",

        "power": f"""⚡ ไอเทมน่าใช้สำหรับบ้านและงานไฟฟ้า

{product['name']}

💰 ราคา {price_text}

ใช้งานง่าย น่ามีติดบ้านไว้
ดูรายละเอียดได้ที่ลิงก์ด้านล่าง 👇

#BENHomeElectrical #อุปกรณ์ไฟฟ้า #ปลั๊กไฟ #ของใช้ในบ้าน""",

        "tools": f"""🛠 ของน่าใช้สำหรับบ้านและงานช่าง

{product['name']}

💰 ราคา {price_text}

ใครกำลังหาอุปกรณ์ดี ๆ ลองดูตัวนี้ได้เลย 👇

#BENHomeElectrical #เครื่องมือช่าง #อุปกรณ์ไฟฟ้า #ของใช้ในบ้าน"""
    }

    return by_cat.get(product["category"], by_cat["power"])


def ai_caption(product):
    if not client:
        return fallback_caption(product)

    price_text = product.get("price_text") or format_price(product["price"])

    prompt = f"""
เขียนโพสต์ Facebook ภาษาไทย สำหรับเพจ BEN Home & Electrical

สินค้า: {product['name']}
ราคา: {price_text}
หมวด: {product['category']}

เงื่อนไข:
- สั้น
- อ่านง่าย
- น่าซื้อ
- โทนแนะนำสินค้าใช้งานจริง
- ใส่ราคาได้
- ถ้าเป็นสินค้าหลายรุ่นให้ใช้คำว่า "ราคาเริ่มต้น"
- ห้ามพูดถึงยอดขาย
- ห้ามบอกว่าขายได้กี่ชิ้น
- ห้ามใส่ hashtag ShopeeAffiliate
- ห้ามใส่ลิงก์ในคำตอบ
- ใส่ hashtag 3-4 อันที่เกี่ยวกับเพจ BEN Home & Electrical
""".strip()

    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content
    except Exception as e:
        print("OPENAI ERROR:", e, flush=True)
        return fallback_caption(product)


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

    groups = {
        "lighting": [p for p in products if p["category"] == "lighting" and p["link"] not in posted],
        "power": [p for p in products if p["category"] == "power" and p["link"] not in posted],
        "tools": [p for p in products if p["category"] == "tools" and p["link"] not in posted],
    }

    non_empty = [g[:15] for g in groups.values() if g]
    if not non_empty:
        print("NO NEW PRODUCT", flush=True)
        return None

    chosen_group = random.choice(non_empty)
    return random.choice(chosen_group)


def run():
    products = load_products()
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
