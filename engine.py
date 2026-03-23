import csv
import json
import os
import time
import requests

MAX_ROWS = 100000
TIMEOUT = 15

PAGE_ID = os.getenv("PAGE_ID", "").strip()
TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()

PAGE_ID_2 = os.getenv("PAGE_ID_2", "").strip()
TOKEN_2 = os.getenv("PAGE_ACCESS_TOKEN_2", "").strip()

CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
USE_OPENAI = os.getenv("USE_OPENAI", "false").strip().lower() == "true"

POSTED_FILE = "posted.json"

session = requests.Session()


def load_posted():
    if not os.path.exists(POSTED_FILE):
        return {"ben": [], "smart": []}
    with open(POSTED_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {"ben": data, "smart": []}
    data.setdefault("ben", [])
    data.setdefault("smart", [])
    return data


def save_posted(data):
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def iter_csv_rows(url):
    print("Streaming CSV once...")
    res = session.get(url, stream=True, timeout=TIMEOUT)
    res.raise_for_status()

    lines = (
        line.decode("utf-8-sig", errors="ignore")
        for line in res.iter_lines()
        if line
    )

    reader = csv.DictReader(lines)

    first_row = True
    for i, row in enumerate(reader, start=1):
        if i > MAX_ROWS:
            print("Reached MAX_ROWS")
            break

        if first_row:
            print("COLUMNS:", list(row.keys()))
            first_row = False

        if i % 5000 == 0:
            print(f"SCANNED: {i}")

        yield row


def pick(row, keys, default=""):
    lower_map = {str(k).strip().lower(): k for k in row.keys()}
    for key in keys:
        real = lower_map.get(key.lower())
        if real is not None:
            value = row.get(real, "")
            if str(value).strip():
                return str(value).strip()
    return default


def to_float(value):
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def classify_product(name):
    t = str(name).lower()

    ben_keywords = [
        "tool", "tools", "เครื่องมือ", "เครื่องมือช่าง", "ไขควง", "คีม", "สว่าน",
        "drill", "multimeter", "tester", "ประแจ", "ค้อน", "เลื่อย", "คัตเตอร์",
        "ตลับเมตร", "หลอดไฟ", "โคมไฟ", "ไฟ led", "ปลั๊กไฟ", "ปลั๊กพ่วง",
        "เบรกเกอร์", "switch", "สายไฟ", "wire", "cable", "adapter", "อะแดปเตอร์"
    ]

    smart_keywords = [
        "camera", "กล้อง", "cctv", "ip camera", "security camera",
        "smart plug", "wifi plug", "ปลั๊กอัจฉริยะ",
        "smart bulb", "หลอดไฟอัจฉริยะ", "wifi bulb",
        "smart switch", "สวิตช์อัจฉริยะ",
        "router", "mesh", "wifi 6", "deco", "เราเตอร์",
        "robot vacuum", "หุ่นยนต์ดูดฝุ่น", "robot mop"
    ]

    if any(k in t for k in smart_keywords):
        return "smart"

    if any(k in t for k in ben_keywords):
        return "ben"

    return None


def scan_best_products():
    posted = load_posted()
    posted_ben = set(posted.get("ben", []))
    posted_smart = set(posted.get("smart", []))

    best_ben = None
    best_ben_score = -1

    best_smart = None
    best_smart_score = -1

    count = 0
    debug_count = 0

    for row in iter_csv_rows(CSV_URL):
        try:
            name = pick(row, ["title", "product_name", "item_name", "name"])
            image = pick(row, [
                "image_link", "image_link_1", "image_link_2", "image_link_3",
                "image_link_4", "image_link_5"
            ])
            sold = to_float(pick(row, [
                "item_sold", "historical_sold", "sold", "sales"
            ], "0"))
            rating = to_float(pick(row, [
                "item_rating", "rating", "product_rating", "shop_rating"
            ], "0"))
            price = to_float(pick(row, [
                "price", "sale_price", "model_prices", "final_price"
            ], "0"))
            com = to_float(pick(row, [
                "commission", "commission_value", "est_commission", "estimated_commission"
            ], "0"))
            link = pick(row, [
                "product_short link", "product_short_link", "short_link",
                "affiliate_link", "product_link", "link"
            ])
            pid = pick(row, ["itemid", "item_id", "product_id", "id"], name)

            count += 1

            if debug_count < 6:
                print("DEBUG:", {
                    "name": name,
                    "sold": sold,
                    "rating": rating,
                    "commission": com,
                    "image": bool(image),
                    "link": bool(link),
                    "class": classify_product(name),
                })
                debug_count += 1

            if not name or not image or not link:
                continue
            if rating < 4.0:
                continue
            if sold < 1:
                continue

            page_class = classify_product(name)
            if not page_class:
                continue

            score = (sold * 2) + (rating * 100) + (com * 5)

            product = {
                "id": pid,
                "name": name,
                "image": image,
                "sold": sold,
                "rating": rating,
                "commission": com,
                "price": price,
                "link": link,
            }

            if page_class == "ben":
                if pid in posted_ben:
                    continue
                if score > best_ben_score:
                    best_ben_score = score
                    best_ben = product

            elif page_class == "smart":
                if pid in posted_smart:
                    continue
                if score > best_smart_score:
                    best_smart_score = score
                    best_smart = product

        except Exception as e:
            print("ROW ERROR:", e)
            continue

    print("SCAN DONE:", count)
    return best_ben, best_smart, posted


def generate_caption_fallback(p, mode):
    if mode == "smart":
        return f"""🏠 ของใช้ Smart Home น่าโดน!

{p['name']}

⭐ {p['rating']} | ขายแล้ว {int(p['sold'])}
👉 เช็กรายละเอียดที่ลิงก์ด้านล่าง

#SmartHome #ของดีบอกต่อ"""
    return f"""🔥 ของมันต้องมี!

{p['name']}

⭐ {p['rating']} | ขายแล้ว {int(p['sold'])}
👉 เช็กรายละเอียดที่ลิงก์ด้านล่าง

#Shopee #ของดีบอกต่อ"""


def generate_caption_openai(p, mode):
    if not USE_OPENAI or not OPENAI_API_KEY:
        return None

    style = "Smart Home / กล้อง / อุปกรณ์บ้านอัจฉริยะ" if mode == "smart" else "เครื่องมือช่าง / ไฟฟ้า / ของใช้ช่าง"

    prompt = f"""
ช่วยเขียนแคปชันขายสินค้า Facebook ภาษาไทย
โทนเพจ: {style}

ข้อมูลสินค้า:
ชื่อสินค้า: {p['name']}
เรตติ้ง: {p['rating']}
ยอดขาย: {int(p['sold'])}
ค่าคอมมิชชั่น: {p['commission']}

เงื่อนไข:
- กระชับ อ่านง่าย
- มี emoji พอประมาณ
- ไม่ใส่ราคาฟันธง
- ปิดท้ายชวนกดลิงก์ด้านล่าง
- hashtag 2-4 อัน
""".strip()

    try:
        res = session.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": "คุณคือผู้ช่วยเขียนแคปชันขายสินค้า Facebook ภาษาไทย"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.8,
            },
            timeout=12,
        )
        res.raise_for_status()
        data = res.json()
        text = data["choices"][0]["message"]["content"].strip()
        if text:
            print(f"OPENAI CAPTION {mode}: success")
            return text
    except Exception as e:
        print(f"OPENAI CAPTION {mode} ERROR:", e)

    return None


def generate_caption(p, mode):
    ai_caption = generate_caption_openai(p, mode)
    if ai_caption:
        return ai_caption
    return generate_caption_fallback(p, mode)


def download_image(url):
    try:
        r = session.get(url, timeout=TIMEOUT)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception as e:
        print("DOWNLOAD IMAGE ERROR:", e)
    return None


def post_image(page_id, token, image_url, caption):
    print("Posting to:", page_id)

    img = download_image(image_url)

    if img:
        try:
            res = session.post(
                f"https://graph.facebook.com/v25.0/{page_id}/photos",
                files={"source": ("img.jpg", img, "image/jpeg")},
                data={
                    "caption": caption,
                    "access_token": token
                },
                timeout=TIMEOUT
            )
            data = res.json()
            print("POST IMAGE:", data)

            if "post_id" in data:
                return data["post_id"]
            if "id" in data:
                return data["id"]

        except Exception as e:
            print("POST IMAGE ERROR:", e)

    try:
        res = session.post(
            f"https://graph.facebook.com/v25.0/{page_id}/feed",
            data={
                "message": caption,
                "access_token": token
            },
            timeout=TIMEOUT
        )
        data = res.json()
        print("POST TEXT:", data)
        return data.get("id")
    except Exception as e:
        print("POST TEXT ERROR:", e)

    return None


def comment_link(post_id, token, link):
    try:
        session.post(
            f"https://graph.facebook.com/v25.0/{post_id}/comments",
            data={
                "message": f"🛒 สั่งซื้อ 👉 {link}",
                "access_token": token
            },
            timeout=TIMEOUT
        )
    except Exception as e:
        print("COMMENT ERROR:", e)


def run_page(page_id, token, product, mode, posted_data):
    print("RUN PAGE:", page_id, mode)

    if not product:
        print(f"❌ No product for {mode}")
        return

    print("✅ CHOSEN:", product["name"])
    print("IMAGE URL:", product["image"])
    print("LINK:", product["link"])

    caption = generate_caption(product, mode)
    post_id = post_image(page_id, token, product["image"], caption)

    if post_id:
        time.sleep(2)
        comment_link(post_id, token, product["link"])

        posted_data.setdefault(mode, [])
        posted_data[mode].append(product["id"])
        posted_data[mode] = posted_data[mode][-5000:]
        save_posted(posted_data)


def run_all_pages():
    best_ben, best_smart, posted_data = scan_best_products()

    if PAGE_ID and TOKEN:
        run_page(PAGE_ID, TOKEN, best_ben, "ben", posted_data)

    if PAGE_ID_2 and TOKEN_2:
        run_page(PAGE_ID_2, TOKEN_2, best_smart, "smart", posted_data)
