import csv
import json
import os
import random
import time
from typing import Dict, Generator, Optional

import requests

MAX_ROWS = 250000
TIMEOUT = 30
POSTED_FILE = "posted.json"

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()

PAGE_ID_2 = os.getenv("PAGE_ID_2", "").strip()
PAGE_ACCESS_TOKEN_2 = os.getenv("PAGE_ACCESS_TOKEN_2", "").strip()

SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
USE_OPENAI = os.getenv("USE_OPENAI", "true").lower() == "true"


# ---------------------------
# storage
# ---------------------------
def load_posted() -> Dict:
    default_data = {
        "ben": {"items": [], "images": [], "titles": []},
        "smart": {"items": [], "images": [], "titles": []},
    }

    if not os.path.exists(POSTED_FILE):
        return default_data

    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        if not isinstance(raw, dict):
            return default_data

        for mode in ["ben", "smart"]:
            raw.setdefault(mode, {})
            raw[mode].setdefault("items", [])
            raw[mode].setdefault("images", [])
            raw[mode].setdefault("titles", [])

        return raw
    except Exception:
        return default_data


def save_posted(data: Dict) -> None:
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_image_key(image_url: str) -> str:
    if not image_url:
        return ""
    return image_url.strip().split("/")[-1].split("?")[0].lower()


def is_duplicate(posted_page_data: Dict, product_id: str, image_key: str, title: str) -> bool:
    if product_id in posted_page_data["items"]:
        return True

    if image_key and image_key in posted_page_data["images"]:
        return True

    head = title[:60].strip().lower()
    for old_title in posted_page_data["titles"]:
        if head and head == old_title[:60].strip().lower():
            return True

    return False


def mark_as_posted(page_mode: str, itemid: str, image_key: str, title: str) -> None:
    posted = load_posted()

    if itemid and itemid not in posted[page_mode]["items"]:
        posted[page_mode]["items"].append(itemid)

    if image_key and image_key not in posted[page_mode]["images"]:
        posted[page_mode]["images"].append(image_key)

    short_title = title[:100].strip()
    if short_title and short_title not in posted[page_mode]["titles"]:
        posted[page_mode]["titles"].append(short_title)

    save_posted(posted)


# ---------------------------
# helpers
# ---------------------------
def to_float(v) -> float:
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def norm_text(v) -> str:
    return str(v or "").strip()


def is_valid_shopee_affiliate_link(link: str) -> bool:
    """
    ยึดตาม product_short link จาก Shopee Product Feed
    รับได้ทั้ง short link และ an_redir จาก feed
    """
    if not link:
        return False

    l = link.strip().lower()

    valid_prefixes = [
        "https://s.shopee.co.th/",
        "https://shope.ee/",
        "https://shopee.co.th/universal-link/",
    ]

    return any(l.startswith(p) for p in valid_prefixes)


def get_affiliate_link(row: Dict) -> str:
    """
    ใช้เฉพาะ product_short link ตาม Shopee Product Feed
    """
    short_link = norm_text(row.get("product_short link"))
    if is_valid_shopee_affiliate_link(short_link):
        return short_link
    return ""


def iter_csv_rows(url: str) -> Generator[Dict, None, None]:
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

            if i >= MAX_ROWS:
                print("Reached MAX_ROWS", flush=True)
                break

            yield row


# ---------------------------
# target filters
# ---------------------------
def is_ben_target(title: str, cat1: str, cat2: str, cat3: str) -> bool:
    text = f"{title} {cat1} {cat2} {cat3}".lower()

    allow_keywords = [
        "electrical", "tools", "tool", "drill", "ไขควง", "สว่าน", "คีม",
        "ปลั๊ก", "ปลั๊กไฟ", "power socket", "รางปลั๊ก", "สายไฟ", "cable",
        "extension", "multimeter", "tester", "switch", "converter", "charger",
        "usb socket", "socket", "power strip", "adapter", "gan", "power bank",
        "แบตเตอรี่", "เครื่องมือ", "ไฟฉาย", "ตะขอ", "กาว", "กาวติดผนัง",
        "พุก", "น็อต", "สกรู", "air purifier filter", "filter"
    ]

    block_keywords = [
        "smart home", "camera", "cctv", "ip camera", "security camera",
        "robot vacuum", "หุ่นยนต์ดูดฝุ่น", "sensor", "doorbell",
        "smart plug", "smart bulb", "smart switch", "mesh", "router",
        "beauty", "สบู่", "soap", "ครีม", "skincare", "camping", "เต็นท์",
        "food", "อาหาร", "fashion", "เสื้อ", "รองเท้า", "watch band",
        "สายนาฬิกา", "garden", "gardening", "การเกษตร", "plant",
        "ผ้าใบ", "กันฝน", "tarp", "tarpaulin", "canvas", "cover", "คลุมรถ",
        "iphone case", "lens protection", "watch strap", "watch active"
    ]

    if any(k in text for k in block_keywords):
        return False

    return any(k in text for k in allow_keywords)


def is_smarthome_target(title: str, cat1: str, cat2: str, cat3: str) -> bool:
    text = f"{title} {cat1} {cat2} {cat3}".lower()

    allow_keywords = [
        "smart", "smart home", "wifi", "camera", "cctv", "ip camera",
        "security camera", "กล้อง", "smart plug", "wifi plug",
        "ปลั๊กอัจฉริยะ", "smart bulb", "smart light", "robot vacuum",
        "หุ่นยนต์ดูดฝุ่น", "sensor", "doorbell", "router", "mesh",
        "smart switch", "lens protection", "camera lens", "full lens",
        "watch strap", "watch active", "redmi watch", "ไฟ led", "led",
        "air purifier", "purifier", "filter"
    ]

    block_keywords = [
        "power socket", "รางปลั๊ก", "ปลั๊กพ่วง", "สายไฟ", "extension cord",
        "drill", "ไขควง", "สว่าน", "คีม", "tester", "multimeter",
        "beauty", "สบู่", "soap", "fashion", "เสื้อ", "รองเท้า",
        "garden", "gardening", "food", "อาหาร",
        "ผ้าใบ", "กันฝน", "tarp", "tarpaulin", "canvas", "cover", "คลุมรถ"
    ]

    if any(k in text for k in block_keywords):
        return False

    return any(k in text for k in allow_keywords)


# ---------------------------
# product builder
# ---------------------------
def build_product(row: Dict) -> Dict:
    title = norm_text(row.get("title"))
    image = norm_text(row.get("image_link"))
    sold = to_float(row.get("item_sold"))
    rating = to_float(row.get("item_rating"))
    price = to_float(row.get("sale_price"))
    itemid = norm_text(row.get("itemid"))

    cat1 = norm_text(row.get("global_category1"))
    cat2 = norm_text(row.get("global_category2"))
    cat3 = norm_text(row.get("global_category3"))

    return {
        "itemid": itemid,
        "title": title,
        "image": image,
        "image_key": normalize_image_key(image),
        "sold": sold,
        "rating": rating,
        "price": price,
        "link": get_affiliate_link(row),
        "cat1": cat1,
        "cat2": cat2,
        "cat3": cat3,
    }


def score_product(row: Dict, page_mode: str) -> float:
    sold = to_float(row.get("item_sold"))
    rating = to_float(row.get("item_rating"))
    price = to_float(row.get("sale_price"))
    title = norm_text(row.get("title")).lower()

    score = (sold * 3.0) + (rating * 120.0)

    if 80 <= price <= 3000:
        score += 25
    if sold >= 500:
        score += 80
    if sold >= 1000:
        score += 120
    if rating >= 4.8:
        score += 50

    hot_words = [
        "usb", "gan", "power bank", "adapter", "ปลั๊ก", "wifi",
        "camera", "lens", "full lens", "smart", "switch", "led",
        "พุก", "กาว", "ตะขอ", "filter"
    ]
    if any(k in title for k in hot_words):
        score += 35

    if page_mode == "smart" and ("camera" in title or "smart" in title or "wifi" in title or "led" in title or "filter" in title):
        score += 25

    if page_mode == "ben" and ("ปลั๊ก" in title or "adapter" in title or "gan" in title or "กาว" in title or "พุก" in title):
        score += 25

    return score


# ---------------------------
# choose product
# ---------------------------
def choose_product(page_mode: str) -> Optional[Dict]:
    posted = load_posted()
    page_history = posted[page_mode]

    best = None
    best_score = -1
    count = 0
    no_short_link_count = 0

    for row in iter_csv_rows(SHOPEE_CSV_URL):
        try:
            title = norm_text(row.get("title"))
            image = norm_text(row.get("image_link"))
            itemid = norm_text(row.get("itemid"))
            sold = to_float(row.get("item_sold"))
            rating = to_float(row.get("item_rating"))

            cat1 = norm_text(row.get("global_category1"))
            cat2 = norm_text(row.get("global_category2"))
            cat3 = norm_text(row.get("global_category3"))

            count += 1

            if not title or not image or not itemid:
                continue

            affiliate_link = get_affiliate_link(row)
            if not affiliate_link:
                no_short_link_count += 1
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

            score = score_product(row, page_mode)

            if score > best_score:
                best_score = score
                best = build_product(row)

        except Exception:
            continue

    print(f"SCAN DONE ({page_mode}): {count}", flush=True)
    print(f"SKIP NO product_short link ({page_mode}): {no_short_link_count}", flush=True)

    if best:
        print(
            f"✅ CHOSEN: {best['title']} | sold={best['sold']} | "
            f"rating={best['rating']} | price={best['price']}",
            flush=True
        )
    else:
        print("❌ No product found with valid Shopee affiliate short link", flush=True)

    return best


# ---------------------------
# caption
# ---------------------------
def make_hook(page_mode: str) -> str:
    ben_hooks = [
        "⚡ คนกำลังมองหาของแนวนี้ กดดูตัวนี้ก่อน",
        "🔥 ของชิ้นนี้กำลังขายดีมากในหมวดงานไฟฟ้า",
        "🛠 สายช่างหรือสายบ้าน ตัวนี้น่ากดดูมาก",
        "👀 ของใช้งานจริง รีวิวดี คนซื้อเยอะ",
        "⚠ ใครกำลังจะซื้อของแนวนี้ ดูตัวนี้ก่อน",
    ]

    smart_hooks = [
        "📱 ของชิ้นนี้กำลังฮิต คนกดดูเยอะมาก",
        "🏠 ของแนว Smart Home ตัวนี้คนซื้อเยอะ",
        "🔥 รีวิวพุ่ง ตัวนี้น่าสนใจมาก",
        "👀 ใครกำลังหาอุปกรณ์ใช้งานคุ้ม ๆ กดดูเลย",
        "⚡ ของใช้งานง่าย ตัวนี้กำลังมาแรง",
    ]

    return random.choice(smart_hooks if page_mode == "smart" else ben_hooks)


def fallback_caption(product: Dict, page_mode: str) -> str:
    hook = make_hook(page_mode)
    sold_text = f"{int(product['sold']):,}"
    rating_text = f"{product['rating']:.2f}"

    return "\n".join([
        hook,
        "",
        product["title"],
        "",
        f"⭐ รีวิว {rating_text}",
        f"🛒 ขายแล้ว {sold_text} ชิ้น",
        "📌 ของกำลังมาแรง คนสนใจเยอะ",
        "",
        "👉 กดดูราคาล่าสุดตรงนี้:",
        product["link"],
    ])


def generate_caption(product: Dict, page_mode: str) -> str:
    if not USE_OPENAI or not OPENAI_API_KEY:
        return fallback_caption(product, page_mode)

    sold_text = f"{int(product['sold']):,}"
    page_desc = "เพจ Smart Home" if page_mode == "smart" else "เพจเครื่องมือช่างและงานไฟฟ้า"

    prompt = f"""
เขียนแคปชัน Facebook ภาษาไทยแบบเพิ่มยอดคลิก สำหรับ {page_desc}

สินค้า:
{product['title']}

ข้อมูล:
- rating: {product['rating']}
- sold: {sold_text}
- หมวด: {product['cat1']} / {product['cat2']} / {product['cat3']}

เงื่อนไข:
- เปิดด้วย hook แรง 1 บรรทัด
- ยาว 5-7 บรรทัด
- อ่านง่าย
- ใช้คำแนว รีวิวเยอะ / ขายดี / กำลังฮิต / น่ากดดู
- ไม่ใส่ราคาตัวเลข
- ไม่ใส่ค่าคอม
- บรรทัดท้ายให้ชวนกดดูราคา
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
                    {"role": "system", "content": "คุณเป็นนักเขียนแคปชันขายของภาษาไทยที่เน้นยอดคลิก"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.9,
            },
            timeout=45,
        )
        res.raise_for_status()
        data = res.json()
        content = data["choices"][0]["message"]["content"].strip()

        if not content:
            return fallback_caption(product, page_mode)

        return f"{content}\n\n👉 กดดูราคาล่าสุดตรงนี้:\n{product['link']}"
    except Exception as e:
        print("OPENAI ERROR:", e, flush=True)
        return fallback_caption(product, page_mode)


# ---------------------------
# posting
# ---------------------------
def post_image(page_id: str, access_token: str, image_url: str, caption: str) -> Optional[str]:
    try:
        res = requests.post(
            f"https://graph.facebook.com/v25.0/{page_id}/photos",
            data={
                "url": image_url,
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
        return None
    except Exception as e:
        print("POST IMAGE ERROR:", e, flush=True)
        return None


def comment_link(post_id: str, access_token: str, link: str) -> None:
    try:
        res = requests.post(
            f"https://graph.facebook.com/v25.0/{post_id}/comments",
            data={
                "message": f"🛒 ลิงก์สั่งซื้ออยู่ตรงนี้\n{link}",
                "access_token": access_token
            },
            timeout=TIMEOUT
        )
        print("COMMENT:", res.json(), flush=True)
    except Exception as e:
        print("COMMENT ERROR:", e, flush=True)


# ---------------------------
# run
# ---------------------------
def run_page(page_mode: str, page_id: str, access_token: str) -> None:
    if not page_id or not access_token:
        print(f"SKIP PAGE ({page_mode}) missing config", flush=True)
        return

    print("RUN PAGE:", page_mode, "***", flush=True)

    product = choose_product(page_mode)
    if not product:
        return

    print("IMAGE URL:", product["image"], flush=True)
    print("LINK:", product["link"], flush=True)

    caption = generate_caption(product, page_mode)
    post_id = post_image(page_id, access_token, product["image"], caption)

    if post_id:
        mark_as_posted(page_mode, product["itemid"], product["image_key"], product["title"])
        time.sleep(3)
        comment_link(post_id, access_token, product["link"])


def run_all_pages() -> None:
    run_page("ben", PAGE_ID, PAGE_ACCESS_TOKEN)
    run_page("smart", PAGE_ID_2, PAGE_ACCESS_TOKEN_2)
