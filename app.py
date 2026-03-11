import os
import csv
import json
import random
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from video_generator import create_product_reel

PAGE_ID = os.environ["PAGE_ID"]
PAGE_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]
CSV_URL = os.environ["SHOPEE_CSV_URL"]
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

POSTED_FILE = "posted_products.json"
LOG_FILE = "post_log.json"

THAI_TIME = ZoneInfo("Asia/Bangkok")

CATEGORY_KEYWORDS = [
    "ไฟ", "หลอดไฟ", "led", "โคมไฟ", "ไฟโซล่า", "solar",
    "ปลั๊ก", "ปลั๊กไฟ", "ปลั๊กพ่วง", "สายไฟ", "สวิตช์", "เบรกเกอร์",
    "ชาร์จ", "charger", "adapter", "power", "battery", "ไฟฉาย",
    "สว่าน", "ไขควง", "ประแจ", "คีม", "มัลติมิเตอร์",
    "เครื่องมือ", "tool", "tools", "diy", "ช่าง", "electrical",
    "socket", "lamp", "light", "home", "living"
]

VIRAL_TOPICS = [
    "ไฟโซล่าดีไหม ใช้ในบ้านคุ้มไหม",
    "ปลั๊กไฟแบบไหนปลอดภัยสำหรับบ้าน",
    "5 เครื่องมือช่างที่ควรมีติดบ้าน",
    "หลอดไฟ LED ประหยัดไฟจริงไหม",
    "อุปกรณ์ไฟฟ้าที่ควรมีติดบ้าน"
]

ENGAGE_TOPICS = [
    "บ้านคุณใช้ปลั๊กไฟกี่จุด",
    "เครื่องมือช่างชิ้นแรกที่ควรมีคืออะไร",
    "ตอนนี้ในบ้านใช้ LED หมดหรือยัง",
    "เคยใช้ไฟโซล่ารอบบ้านไหม",
    "ของใช้ไฟฟ้าที่ขาดไม่ได้คืออะไร"
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


def normalize_posted(raw):
    if not isinstance(raw, list):
        return []

    out = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            link = item.get("link")
            if isinstance(link, str) and link.strip():
                out.append(link.strip())

    return list(dict.fromkeys(out))


def save_posted_link(link):
    posted = normalize_posted(load_json(POSTED_FILE, []))
    posted.append(link)
    save_json(POSTED_FILE, list(dict.fromkeys(posted)))


def log_post(post_type, content, post_id=""):
    logs = load_json(LOG_FILE, [])
    if not isinstance(logs, list):
        logs = []

    row = {
        "time": str(datetime.now(THAI_TIME)),
        "type": post_type,
        "post_id": post_id
    }

    if isinstance(content, dict):
        row.update({
            "name": content.get("name", ""),
            "link": content.get("link", ""),
            "rating": content.get("rating", 0),
            "sold": content.get("sold", 0),
        })
    else:
        row["text"] = str(content)

    logs.append(row)
    save_json(LOG_FILE, logs)


def get_mode():
    now = datetime.now(THAI_TIME)
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
        return "reels"

    return "product"


def is_match(name, row):
    text = " ".join([
        (name or "").lower(),
        str(row.get("global_category1", "")).lower(),
        str(row.get("global_category2", "")).lower(),
        str(row.get("global_category3", "")).lower(),
    ])
    return any(k.lower() in text for k in CATEGORY_KEYWORDS)


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
            "rating": rating,
            "sold": sold
        })

        if len(products) >= 300:
            break

    print("CSV SCANNED:", scanned, flush=True)
    print("CSV PRODUCTS:", len(products), flush=True)
    return products


def pick_product(products):
    posted = set(normalize_posted(load_json(POSTED_FILE, [])))
    candidates = [p for p in products if p["link"] not in posted]

    if not candidates:
        print("NO NEW PRODUCT", flush=True)
        return None

    candidates.sort(key=lambda x: (x["rating"], x["sold"]), reverse=True)
    top = candidates[:40] if len(candidates) >= 40 else candidates
    return random.choice(top)


def ai_text(prompt, fallback):
    if not OPENAI_KEY:
        return fallback

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


def build_product_caption(product):
    fallback = f"""🔥 {product['name']}

ของน่าใช้สำหรับบ้านและงานไฟฟ้า
เช็กราคาล่าสุดที่ลิงก์ด้านล่าง 👇"""

    prompt = f"""
เขียนโพสต์ Facebook ภาษาไทย สำหรับเพจ BEN Home & Electrical

สินค้า: {product['name']}

เงื่อนไข:
- สั้น
- อ่านง่าย
- น่าคลิก
- ห้ามใส่ราคา
- ห้ามพูดยอดขาย
- โทนเหมือนแนะนำของใช้ไฟฟ้าและเครื่องมือช่าง
- ให้ชวนคนไปเช็กราคาล่าสุดที่ลิงก์
""".strip()

    text = ai_text(prompt, fallback).strip()

    return f"""{text}

🛒 สั่งซื้อสินค้า
{product['link']}"""


def build_viral():
    topic = random.choice(VIRAL_TOPICS)
    fallback = f"""⚡ {topic}

ใครเคยใช้บ้าง มาแชร์กัน 👇"""

    prompt = f"""
เขียนโพสต์ Facebook ภาษาไทย สำหรับเพจ BEN Home & Electrical

หัวข้อ: {topic}

เงื่อนไข:
- สั้น
- ชวนคอมเมนต์
- ไม่ขายของ
- แนวให้ความรู้เรื่องไฟฟ้าและของใช้ในบ้าน
""".strip()

    return ai_text(prompt, fallback)


def build_engage():
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


def build_reels_caption(product):
    fallback = f"""🔥 {product['name']}

เช็กราคาล่าสุดที่ลิงก์ด้านล่าง 👇

🛒 สั่งซื้อสินค้า
{product['link']}"""

    prompt = f"""
เขียน caption Reels ภาษาไทย สำหรับเพจ BEN Home & Electrical

สินค้า: {product['name']}

เงื่อนไข:
- สั้น
- ดูเป็นคลิปแนะนำสินค้า
- ห้ามใส่ราคา
- ห้ามพูดยอดขาย
- ปิดท้ายชวนเช็กราคาล่าสุดที่ลิงก์
""".strip()

    return ai_text(prompt, fallback)


def post_photo(image, caption):
    print("STEP: facebook photo post", flush=True)

    r = requests.post(
        f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos",
        data={
            "url": image,
            "caption": caption,
            "access_token": PAGE_TOKEN
        },
        timeout=30
    )

    try:
        data = r.json()
    except Exception:
        print("POST RAW:", r.text, flush=True)
        return {}

    print("POST RESPONSE:", data, flush=True)
    return data


def post_text(message):
    print("STEP: facebook text post", flush=True)

    r = requests.post(
        f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed",
        data={
            "message": message,
            "access_token": PAGE_TOKEN
        },
        timeout=30
    )

    try:
        data = r.json()
    except Exception:
        print("POST RAW:", r.text, flush=True)
        return {}

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


def upload_reel(product):
    print("STEP: create reel video", flush=True)
    video_path = create_product_reel(product["image"], product["name"], "reel.mp4")

    start_url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/video_reels"

    start_res = requests.post(
        start_url,
        data={
            "upload_phase": "start",
            "access_token": PAGE_TOKEN
        },
        timeout=30
    ).json()

    print("REEL START:", start_res, flush=True)

    video_id = start_res.get("video_id")
    upload_url = start_res.get("upload_url")

    if not video_id or not upload_url:
        return {}

    with open(video_path, "rb") as f:
        upload_res = requests.post(
            upload_url,
            data=f,
            headers={"Authorization": f"OAuth {PAGE_TOKEN}"},
            timeout=120
        )

    print("REEL UPLOAD:", upload_res.text, flush=True)

    finish_res = requests.post(
        start_url,
        data={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": build_reels_caption(product),
            "access_token": PAGE_TOKEN
        },
        timeout=30
    )

    try:
        data = finish_res.json()
    except Exception:
        print("REEL FINISH RAW:", finish_res.text, flush=True)
        return {}

    print("REEL FINISH:", data, flush=True)
    return {"id": video_id, **data}


def run_product():
    products = load_csv_products()
    if not products:
        return

    product = pick_product(products)
    if not product:
        return

    res = post_photo(product["image"], build_product_caption(product))
    post_id = res.get("post_id") or res.get("id")

    if not post_id:
        return

    comment_link(post_id, product["link"])
    save_posted_link(product["link"])
    log_post("product", product, post_id)
    print("POST SUCCESS", flush=True)


def run_viral():
    res = post_text(build_viral())
    post_id = res.get("id") or ""
    log_post("viral", "viral", post_id)
    print("POST SUCCESS", flush=True)


def run_engage():
    res = post_text(build_engage())
    post_id = res.get("id") or ""
    log_post("engage", "engage", post_id)
    print("POST SUCCESS", flush=True)


def run_reels():
    products = load_csv_products()
    if not products:
        return

    product = pick_product(products)
    if not product:
        return

    res = upload_reel(product)
    reel_id = res.get("id") or res.get("video_id") or ""

    if reel_id:
        save_posted_link(product["link"])
        log_post("reels", product, reel_id)
        print("REEL SUCCESS", flush=True)


def run():
    mode = get_mode()
    print("MODE:", mode, flush=True)

    if mode == "viral":
        run_viral()
        return

    if mode == "engage":
        run_engage()
        return

    if mode == "reels":
        run_reels()
        return

    run_product()


if __name__ == "__main__":
    run()
