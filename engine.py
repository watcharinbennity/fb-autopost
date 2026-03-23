import csv
import json
import os
import time
import requests

MAX_ROWS = 100000
TIMEOUT = 20

PAGE_ID = os.getenv("PAGE_ID", "").strip()
TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()

PAGE_ID_2 = os.getenv("PAGE_ID_2", "").strip()
TOKEN_2 = os.getenv("PAGE_ACCESS_TOKEN_2", "").strip()

CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
USE_OPENAI = os.getenv("USE_OPENAI", "true").lower() == "true"

POSTED_FILE = "posted.json"


# ---------------- STORAGE ----------------
def load_posted():
    if not os.path.exists(POSTED_FILE):
        return set()
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_posted(data):
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(data), f, ensure_ascii=False)


# ---------------- CSV STREAM ----------------
def iter_csv_rows(url):
    try:
        print("Streaming CSV...", flush=True)

        with requests.get(url, stream=True, timeout=(20, 120)) as res:
            res.raise_for_status()

            lines = (
                line.decode("utf-8-sig", errors="ignore")
                for line in res.iter_lines()
                if line
            )

            reader = csv.DictReader(lines)

            for i, row in enumerate(reader, start=1):
                if i % 5000 == 0:
                    print(f"streamed_rows={i}", flush=True)

                if i > MAX_ROWS:
                    print("Reached MAX_ROWS", flush=True)
                    break

                yield row

    except Exception as e:
        print("CSV ERROR:", e, flush=True)


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


# ---------------- TARGET FILTER ----------------
def is_target_product(name):
    n = name.lower()

    camera_keywords = [
        "camera", "กล้อง", "cctv", "ip camera", "wifi camera", "security camera"
    ]
    robot_keywords = [
        "robot vacuum", "หุ่นยนต์ดูดฝุ่น", "robot mop"
    ]
    plug_keywords = [
        "smart plug", "wifi plug", "ปลั๊ก", "ปลั๊กอัจฉริยะ"
    ]

    if any(k in n for k in camera_keywords):
        return "camera"

    if any(k in n for k in robot_keywords):
        return "robot"

    if any(k in n for k in plug_keywords):
        return "plug"

    return None


# ---------------- SELECT PRODUCT ----------------
def choose_product():
    posted = load_posted()
    best = None
    best_score = -1
    count = 0

    for row in iter_csv_rows(CSV_URL):
        try:
            name = pick(row, [
                "product_name", "item_name", "name", "title"
            ])
            image = pick(row, [
                "image_url", "image", "main_image", "product_image"
            ])
            sold = to_float(pick(row, [
                "historical_sold", "sold", "sales"
            ], "0"))
            rating = to_float(pick(row, [
                "rating", "item_rating", "product_rating", "avg_rating"
            ], "0"))
            price = to_float(pick(row, [
                "price", "final_price", "product_price", "sale_price"
            ], "0"))
            commission = to_float(pick(row, [
                "commission", "commission_value", "est_commission", "estimated_commission"
            ], "0"))
            link = pick(row, [
                "product_short link", "product_short_link",
                "short_link", "affiliate_link", "link", "product_link"
            ])
            pid = pick(row, [
                "itemid", "item_id", "product_id", "id"
            ], name)

            count += 1

            if not name or not image or not link:
                continue

            group = is_target_product(name)
            if not group:
                continue

            if rating < 4.0:
                continue

            if pid in posted:
                continue

            # filter แบบไม่โหดเกิน
            if group == "camera" and sold < 100:
                continue
            if group == "robot" and sold < 30:
                continue
            if group == "plug" and sold < 200:
                continue

            # ถ้ามีค่าคอม ให้ใช้ ถ้าไม่มีก็ยังไม่ตัดทิ้ง
            score = (sold * 2) + (rating * 100) + (commission * 5)

            if score > best_score:
                best_score = score
                best = {
                    "id": pid,
                    "name": name,
                    "image": image,
                    "sold": sold,
                    "rating": rating,
                    "price": price,
                    "commission": commission,
                    "link": link,
                    "group": group,
                }

        except Exception:
            continue

    print("SCAN DONE:", count, flush=True)

    if best:
        posted.add(best["id"])
        save_posted(posted)

    return best


# ---------------- OPENAI CAPTION ----------------
def fallback_caption(p):
    return f"""🔥 ของมันต้องมี!

{p['name']}

⭐ {p['rating']} | ขายแล้ว {int(p['sold'])}
💸 คุ้มสุดตอนนี้!

👉 เช็กราคาล่าสุดที่ลิงก์ด้านล่าง

#Shopee #ของดีบอกต่อ"""


def generate_caption(p):
    if not USE_OPENAI or not OPENAI_API_KEY:
        return fallback_caption(p)

    prompt = f"""
เขียนแคปชัน Facebook ภาษาไทย สำหรับขายสินค้า

สินค้า:
{p['name']}

ข้อมูล:
- rating: {p['rating']}
- sold: {int(p['sold'])}
- group: {p['group']}

เงื่อนไข:
- เขียนให้กระชับ น่าอ่าน
- แนวขายจริง ไม่เวอร์เกินไป
- ไม่ใส่ราคาตัวเลข
- 4-6 บรรทัด
- ปิดท้ายด้วยชวนกดดูรายละเอียดที่ลิงก์ด้านล่าง
- ห้ามใส่ลิงก์เอง
""".strip()

    try:
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": "คุณเป็นนักเขียนแคปชันขายของภาษาไทย"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.9,
            },
            timeout=45,
        )
        res.raise_for_status()
        data = res.json()
        text = data["choices"][0]["message"]["content"].strip()

        if not text:
            return fallback_caption(p)

        return text
    except Exception as e:
        print("OPENAI ERROR:", e, flush=True)
        return fallback_caption(p)


# ---------------- IMAGE ----------------
def download_image(url):
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception as e:
        print("DOWNLOAD IMAGE ERROR:", e, flush=True)
    return None


# ---------------- POST ----------------
def post_image(page_id, token, image_url, caption):
    print("Posting to:", page_id, flush=True)

    img = download_image(image_url)

    if img:
        try:
            res = requests.post(
                f"https://graph.facebook.com/v25.0/{page_id}/photos",
                files={"source": ("img.jpg", img, "image/jpeg")},
                data={
                    "caption": caption,
                    "access_token": token
                },
                timeout=TIMEOUT
            )

            data = res.json()
            print("POST IMAGE:", data, flush=True)

            if "post_id" in data:
                return data["post_id"]

            if "id" in data:
                return data["id"]

        except Exception as e:
            print("POST IMAGE ERROR:", e, flush=True)

    # fallback text
    try:
        res = requests.post(
            f"https://graph.facebook.com/v25.0/{page_id}/feed",
            data={
                "message": caption,
                "access_token": token
            },
            timeout=TIMEOUT
        )

        data = res.json()
        print("POST TEXT:", data, flush=True)

        return data.get("id")
    except Exception as e:
        print("POST TEXT ERROR:", e, flush=True)

    return None


# ---------------- COMMENT ----------------
def comment_link(post_id, token, link):
    try:
        requests.post(
            f"https://graph.facebook.com/v25.0/{post_id}/comments",
            data={
                "message": f"🛒 สั่งซื้อ 👉 {link}",
                "access_token": token
            },
            timeout=TIMEOUT
        )
    except Exception as e:
        print("COMMENT ERROR:", e, flush=True)


# ---------------- RUN ----------------
def run_page(page_id, token):
    print("RUN PAGE:", page_id, flush=True)

    product = choose_product()

    if not product:
        print("❌ No product", flush=True)
        return

    print("✅ CHOSEN:", product["name"], flush=True)
    print("IMAGE URL:", product["image"], flush=True)
    print("LINK:", product["link"], flush=True)

    caption = generate_caption(product)

    post_id = post_image(page_id, token, product["image"], caption)

    if post_id:
        time.sleep(3)
        comment_link(post_id, token, product["link"])


def run_all_pages():
    run_page(PAGE_ID, TOKEN)

    if PAGE_ID_2 and TOKEN_2:
        run_page(PAGE_ID_2, TOKEN_2)
