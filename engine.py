import csv
import json
import os
import time
import requests

MAX_ROWS = 600000
TIMEOUT = 20

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()

PAGE_ID_2 = os.getenv("PAGE_ID_2", "").strip()
PAGE_ACCESS_TOKEN_2 = os.getenv("PAGE_ACCESS_TOKEN_2", "").strip()

SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
USE_OPENAI = os.getenv("USE_OPENAI", "true").lower() == "true"

POSTED_FILE = "posted.json"


def load_posted():
    default_data = {
        "ben": {"items": [], "images": [], "titles": []},
        "smart": {"items": [], "images": [], "titles": []},
    }

    if not os.path.exists(POSTED_FILE):
        return default_data

    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        if isinstance(raw, list):
            return default_data

        for mode in ["ben", "smart"]:
            raw.setdefault(mode, {})
            raw[mode].setdefault("items", [])
            raw[mode].setdefault("images", [])
            raw[mode].setdefault("titles", [])

        return raw

    except Exception:
        return default_data


def save_posted(data):
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_image_key(image_url: str) -> str:
    if not image_url:
        return ""
    return image_url.strip().split("/")[-1].split("?")[0].lower()


def is_duplicate(posted_page_data, product_id, image_key, title):
    if product_id in posted_page_data["items"]:
        return True

    if image_key and image_key in posted_page_data["images"]:
        return True

    title_head = title[:60].strip().lower()
    for old_title in posted_page_data["titles"]:
        if title_head and title_head == old_title[:60].strip().lower():
            return True

    return False


def mark_as_posted(page_mode, itemid, image_key, title):
    posted = load_posted()

    if itemid and itemid not in posted[page_mode]["items"]:
        posted[page_mode]["items"].append(itemid)

    if image_key and image_key not in posted[page_mode]["images"]:
        posted[page_mode]["images"].append(image_key)

    short_title = title[:100].strip()
    if short_title and short_title not in posted[page_mode]["titles"]:
        posted[page_mode]["titles"].append(short_title)

    save_posted(posted)


def to_float(v):
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def norm_text(v):
    return str(v or "").strip()


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


def is_ben_target(title, cat1, cat2, cat3):
    text = f"{title} {cat1} {cat2} {cat3}".lower()

    allow_keywords = [
        "electrical", "tools", "tool", "drill", "ไขควง", "สว่าน", "คีม",
        "ปลั๊ก", "ปลั๊กไฟ", "power socket", "รางปลั๊ก", "สายไฟ", "cable",
        "extension", "multimeter", "tester", "switch", "converter", "charger",
        "usb socket", "socket", "power strip"
    ]

    block_keywords = [
        "smart home", "camera", "cctv", "ip camera", "security camera",
        "robot vacuum", "หุ่นยนต์ดูดฝุ่น", "sensor", "doorbell",
        "smart plug", "smart bulb", "smart switch", "mesh", "router",
        "beauty", "สบู่", "soap", "ครีม", "skincare", "camping", "เต็นท์",
        "food", "อาหาร", "fashion", "เสื้อ", "รองเท้า", "watch band",
        "สายนาฬิกา", "garden", "gardening", "การเกษตร", "plant"
    ]

    if any(k in text for k in block_keywords):
        return False

    return any(k in text for k in allow_keywords)


def is_smarthome_target(title, cat1, cat2, cat3):
    text = f"{title} {cat1} {cat2} {cat3}".lower()

    allow_keywords = [
        "smart", "smart home", "wifi", "camera", "cctv", "ip camera",
        "security camera", "กล้อง", "smart plug", "wifi plug",
        "ปลั๊กอัจฉริยะ", "smart bulb", "smart light", "robot vacuum",
        "หุ่นยนต์ดูดฝุ่น", "sensor", "doorbell", "router", "mesh",
        "smart switch"
    ]

    block_keywords = [
        "power socket", "รางปลั๊ก", "ปลั๊กพ่วง", "สายไฟ", "extension cord",
        "drill", "ไขควง", "สว่าน", "คีม", "tester", "multimeter",
        "beauty", "สบู่", "soap", "fashion", "เสื้อ", "รองเท้า",
        "garden", "gardening", "food", "อาหาร", "watch band", "สายนาฬิกา"
    ]

    if any(k in text for k in block_keywords):
        return False

    return any(k in text for k in allow_keywords)


def choose_product(page_mode):
    posted = load_posted()
    page_history = posted[page_mode]

    best = None
    best_score = -1
    count = 0

    for row in iter_csv_rows(SHOPEE_CSV_URL):
        try:
            title = norm_text(row.get("title"))
            image = norm_text(row.get("image_link"))
            sold = to_float(row.get("item_sold"))
            rating = to_float(row.get("item_rating"))
            price = to_float(row.get("sale_price"))
            product_link = norm_text(row.get("product_link"))
            short_link = norm_text(row.get("product_short link"))
            itemid = norm_text(row.get("itemid"))

            cat1 = norm_text(row.get("global_category1"))
            cat2 = norm_text(row.get("global_category2"))
            cat3 = norm_text(row.get("global_category3"))

            count += 1

            if not title or not itemid or not image:
                continue

            link = short_link or product_link
            if not link:
                continue

            if rating < 4.0:
                continue

            if sold < 20:
                continue

            image_key = normalize_image_key(image)

            if is_duplicate(page_history, itemid, image_key, title):
                continue

            if page_mode == "ben":
                if not is_ben_target(title, cat1, cat2, cat3):
                    continue
            elif page_mode == "smart":
                if not is_smarthome_target(title, cat1, cat2, cat3):
                    continue

            score = (sold * 2.0) + (rating * 100.0)

            if 80 <= price <= 3000:
                score += 25

            if score > best_score:
                best_score = score
                best = {
                    "itemid": itemid,
                    "title": title,
                    "image": image,
                    "image_key": image_key,
                    "sold": sold,
                    "rating": rating,
                    "price": price,
                    "link": link,
                    "cat1": cat1,
                    "cat2": cat2,
                    "cat3": cat3,
                }

                if score > 800:
                    break

        except Exception:
            continue

    print(f"SCAN DONE ({page_mode}): {count}", flush=True)
    return best


def fallback_caption(product, page_mode):
    if page_mode == "smart":
        return f"""🔥 ของมันต้องมี!

{product['title']}

⭐ {product['rating']} | ขายแล้ว {int(product['sold'])}
🏠 ตัวช่วยเพิ่มความสะดวกให้บ้านของคุณ

👉 เช็กราคาล่าสุด:
{product['link']}

#Shopee #SmartHome"""
    else:
        return f"""🔥 ของมันต้องมี!

{product['title']}

⭐ {product['rating']} | ขายแล้ว {int(product['sold'])}
🛠 ของดีน่าใช้สำหรับงานช่างและงานไฟฟ้า

👉 เช็กราคาล่าสุด:
{product['link']}

#Shopee #ของดีบอกต่อ"""


def generate_caption(product, page_mode):
    if not USE_OPENAI or not OPENAI_API_KEY:
        return fallback_caption(product, page_mode)

    page_desc = "เพจ Smart Home" if page_mode == "smart" else "เพจเครื่องมือช่างและไฟฟ้า"

    prompt = f"""
เขียนแคปชัน Facebook ภาษาไทย สำหรับ {page_desc}

สินค้า:
{product['title']}

ข้อมูล:
- rating: {product['rating']}
- sold: {int(product['sold'])}
- หมวด: {product['cat1']} / {product['cat2']} / {product['cat3']}

เงื่อนไข:
- สั้น กระชับ น่าอ่าน
- 4-6 บรรทัด
- แนวขายจริง ไม่เวอร์เกินไป
- ไม่ใส่ราคาตัวเลข
- ห้ามใส่ลิงก์เองในเนื้อหา
- เดี๋ยวระบบจะเติมลิงก์ให้ท้ายโพสต์
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
                "temperature": 0.8,
            },
            timeout=45,
        )
        res.raise_for_status()
        data = res.json()
        content = data["choices"][0]["message"]["content"].strip()

        if not content:
            return fallback_caption(product, page_mode)

        return f"""{content}

👉 เช็กราคาล่าสุด:
{product['link']}"""
    except Exception as e:
        print("OPENAI ERROR:", e, flush=True)
        return fallback_caption(product, page_mode)


def download_image(url):
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception as e:
        print("DOWNLOAD IMAGE ERROR:", e, flush=True)
    return None


def post_product(page_id, access_token, product, caption):
    print("Posting to:", page_id, flush=True)

    img = download_image(product["image"])

    if img:
        try:
            res = requests.post(
                f"https://graph.facebook.com/v25.0/{page_id}/photos",
                files={"source": ("img.jpg", img, "image/jpeg")},
                data={
                    "caption": caption,
                    "access_token": access_token
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

    try:
        res = requests.post(
            f"https://graph.facebook.com/v25.0/{page_id}/feed",
            data={
                "message": caption,
                "access_token": access_token
            },
            timeout=TIMEOUT
        )
        data = res.json()
        print("POST TEXT:", data, flush=True)
        return data.get("id")
    except Exception as e:
        print("POST TEXT ERROR:", e, flush=True)
        return None


def comment_link(post_id, access_token, link):
    try:
        res = requests.post(
            f"https://graph.facebook.com/v25.0/{post_id}/comments",
            data={
                "message": f"🛒 สั่งซื้อสินค้า\n{link}",
                "access_token": access_token
            },
            timeout=TIMEOUT
        )
        print("COMMENT:", res.json(), flush=True)
    except Exception as e:
        print("COMMENT ERROR:", e, flush=True)


def run_page(page_mode, page_id, access_token):
    if not page_id or not access_token:
        print(f"SKIP PAGE ({page_mode}) missing config", flush=True)
        return None

    print("RUN PAGE:", page_mode, page_id, flush=True)

    product = choose_product(page_mode)

    if not product:
        print("❌ No product", flush=True)
        return None

    print("✅ CHOSEN:", product["title"], flush=True)
    print("IMAGE URL:", product["image"], flush=True)
    print("LINK:", product["link"], flush=True)

    caption = generate_caption(product, page_mode)
    post_id = post_product(page_id, access_token, product, caption)

    if post_id:
        mark_as_posted(page_mode, product["itemid"], product["image_key"], product["title"])
        time.sleep(3)
        comment_link(post_id, access_token, product["link"])

    return product


def run_all_pages():
    run_page("ben", PAGE_ID, PAGE_ACCESS_TOKEN)
    run_page("smart", PAGE_ID_2, PAGE_ACCESS_TOKEN_2)
