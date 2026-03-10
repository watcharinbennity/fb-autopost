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

# หมวดที่ตรงกับเพจ BEN Home & Electrical
CATEGORY_KEYWORDS = [
    "ไฟ", "หลอดไฟ", "led", "โคมไฟ", "ไฟโซล่า", "solar",
    "ปลั๊ก", "ปลั๊กไฟ", "ปลั๊กพ่วง", "สายไฟ", "สวิตช์", "เบรกเกอร์",
    "ชาร์จ", "charger", "adapter", "power", "battery", "ไฟฉาย",
    "สว่าน", "ไขควง", "ประแจ", "คีม", "มัลติมิเตอร์",
    "เครื่องมือ", "tool", "tools", "diy", "ช่าง", "electrical"
]

VIRAL_TOPICS = [
    "ไฟโซล่าดีไหม ใช้ในบ้านคุ้มไหม",
    "ปลั๊กไฟแบบไหนปลอดภัยสำหรับบ้าน",
    "5 เครื่องมือช่างที่ควรมีติดบ้าน",
    "หลอดไฟ LED ประหยัดไฟจริงไหม",
    "อุปกรณ์ไฟฟ้าอะไรที่ควรมีติดบ้าน"
]

ENGAGE_TOPICS = [
    "บ้านคุณใช้ปลั๊กไฟกี่จุดในห้องนั่งเล่น",
    "เครื่องมือช่างชิ้นแรกที่ควรมีติดบ้านคืออะไร",
    "เคยใช้ไฟโซล่ารอบบ้านกันไหม",
    "ตอนนี้ในบ้านใช้หลอด LED กันครบหรือยัง",
    "ของใช้ไฟฟ้าชิ้นไหนสำคัญสุดสำหรับบ้านคุณ"
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


def normalize_posted(raw):
    if not isinstance(raw, list):
        return []
    cleaned = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip())
        elif isinstance(item, dict):
            link = item.get("link")
            if isinstance(link, str) and link.strip():
                cleaned.append(link.strip())
    return list(dict.fromkeys(cleaned))


def log_post(post_type, content, post_id=""):
    logs = load_json(LOG_FILE, [])
    if not isinstance(logs, list):
        logs = []

    row = {
        "time": str(datetime.now(TH_TZ)),
        "type": post_type,
        "post_id": post_id,
    }

    if isinstance(content, dict):
        row.update({
            "name": content.get("name", ""),
            "price": content.get("price", 0),
            "link": content.get("link", ""),
            "rating": content.get("rating", 0),
            "sold": content.get("sold", 0),
        })
    else:
        row["text"] = str(content)

    logs.append(row)
    save_json(LOG_FILE, logs)


def get_mode():
    now = datetime.now(TH_TZ)
    hm = now.hour * 60 + now.minute

    if 9 * 60 <= hm < 10 * 60:
        return "viral"
    if 12 * 60 <= hm < 13 * 60:
        return "product"
    if 15 * 60 <= hm < 16 * 60:
        return "engage"
    if 18 * 60 + 30 <= hm < 19 * 60 + 30:
        return "product"
    if 21 * 60 <= hm < 22 * 60:
        return "product"

    # manual run
    return "product"


def is_relevant_product(row, name):
    c1 = (row.get("global_category1") or "").strip().lower()
    c2 = (row.get("global_category2") or "").strip().lower()
    c3 = (row.get("global_category3") or "").strip().lower()
    text = f"{name.lower()} {c1} {c2} {c3}"

    return any(k.lower() in text for k in CATEGORY_KEYWORDS)


def load_csv_products(max_scan_rows=100000, max_candidates=500):
    print("STEP: load csv", flush=True)

    try:
        r = requests.get(CSV_URL, stream=True, timeout=(15, 90))
        r.raise_for_status()

        decoded_lines = (
            line.decode("utf-8", errors="ignore")
            for line in r.iter_lines()
            if line
        )

        reader = csv.DictReader(decoded_lines)

        products = []
        scanned = 0

        for row in reader:
            scanned += 1
            if scanned > max_scan_rows:
                break

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
                "sold": sold,
            })

            if len(products) >= max_candidates:
                break

        print("CSV SCANNED:", scanned, flush=True)
        print("CSV PRODUCTS:", len(products), flush=True)
        return products

    except Exception as e:
        print("CSV ERROR:", e, flush=True)
        return []


def pick_product(products):
    posted = set(normalize_posted(load_json(POSTED_FILE, [])))
    candidates = [p for p in products if p["link"] not in posted]

    if not candidates:
        print("NO NEW PRODUCT", flush=True)
        return None

    # เน้นสินค้ามีโอกาสขายและดูดี
    candidates.sort(
        key=lambda x: (
            parse_float(x.get("rating", 0)),
            parse_int(x.get("sold", 0)),
            -abs(parse_float(x.get("price", 0)) - 199)  # ดันช่วงราคากลาง ๆ
        ),
        reverse=True
    )

    top = candidates[:50] if len(candidates) >= 50 else candidates
    return random.choice(top)


def ai_text(prompt, fallback):
    if not OPENAI_KEY:
        return fallback

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


def build_product_caption(product):
    price_text = format_price(product.get("price", 0))

    fallback = f"""🔥 {product['name']}

💰 ราคา {price_text}

ของน่าใช้สำหรับบ้านและงานไฟฟ้า
ดูสินค้าได้ที่ลิงก์ด้านล่าง 👇"""

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

    base = ai_text(prompt, fallback).strip()

    return f"""{base}

🛒 สั่งซื้อสินค้า
{product['link']}"""


def build_viral_caption():
    topic = random.choice(VIRAL_TOPICS)

    fallback = f"""⚡ {topic}

ใครใช้อยู่บ้าง มาแชร์กันหน่อย 👇"""

    prompt = f"""
เขียนโพสต์ Facebook ภาษาไทย สำหรับเพจ BEN Home & Electrical

หัวข้อ: {topic}

เงื่อนไข:
- สั้น
- ชวนคอมเมนต์
- ไม่ขายของตรงเกินไป
- เหมือนเพจให้ความรู้เรื่องอุปกรณ์ไฟฟ้าและของใช้ในบ้าน
""".strip()

    return ai_text(prompt, fallback)


def build_engage_caption():
    topic = random.choice(ENGAGE_TOPICS)

    fallback = f"""{topic}

คอมเมนต์กันหน่อย 👇"""

    prompt = f"""
เขียนโพสต์ Facebook ภาษาไทย สำหรับเพจ BEN Home & Electrical

หัวข้อ: {topic}

เงื่อนไข:
- สั้น
- ชวนคนตอบ
- กันเอง
- ไม่ขายของ
""".strip()

    return ai_text(prompt, fallback)


def post_photo_by_url(image_url, caption):
    print("STEP: facebook post", flush=True)

    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"
    payload = {
        "url": image_url,
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


def post_text_only(caption):
    print("STEP: facebook text post", flush=True)

    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    payload = {
        "message": caption,
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


def save_posted_link(link):
    posted = normalize_posted(load_json(POSTED_FILE, []))
    posted.append(link)
    save_json(POSTED_FILE, list(dict.fromkeys(posted)))


def run_product():
    products = load_csv_products()

    if not products:
        print("NO PRODUCTS", flush=True)
        return

    product = pick_product(products)
    if not product:
        return

    caption = build_product_caption(product)
    res = post_photo_by_url(product["image"], caption)

    post_id = res.get("post_id") or res.get("id")
    if not post_id:
        print("POST FAIL", res, flush=True)
        return

    comment_link(post_id, product["link"])
    save_posted_link(product["link"])
    log_post("product", product, post_id)
    print("POST SUCCESS", flush=True)


def run_viral():
    caption = build_viral_caption()
    res = post_text_only(caption)

    post_id = res.get("id") or ""
    log_post("viral", caption, post_id)
    print("POST SUCCESS", flush=True)


def run_engage():
    caption = build_engage_caption()
    res = post_text_only(caption)

    post_id = res.get("id") or ""
    log_post("engage", caption, post_id)
    print("POST SUCCESS", flush=True)


def run():
    mode = get_mode()
    print("MODE:", mode, flush=True)

    if mode == "viral":
        run_viral()
        return

    if mode == "engage":
        run_engage()
        return

    run_product()


if __name__ == "__main__":
    run()
