import csv
import json
import os
import random
import time
from typing import Dict, Generator, Optional
from urllib.parse import quote

import requests

MAX_ROWS = 250000
TIMEOUT = 30
POSTED_FILE = "posted.json"
REPLIED_FILE = "replied_comments.json"

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()

PAGE_ID_2 = os.getenv("PAGE_ID_2", "").strip()
PAGE_ACCESS_TOKEN_2 = os.getenv("PAGE_ACCESS_TOKEN_2", "").strip()

SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()
SHOPEE_AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "").strip()
SHOPEE_SUB_ID_PREFIX = os.getenv("SHOPEE_SUB_ID_PREFIX", "fbbot").strip()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
USE_OPENAI = os.getenv("USE_OPENAI", "true").lower() == "true"

SHORTENER_BASE_URL = os.getenv(
    "SHORTENER_BASE_URL",
    "https://ben-shortener.bennity.workers.dev"
).strip()

AUTO_REPLY_COMMENTS = os.getenv("AUTO_REPLY_COMMENTS", "true").lower() == "true"
COMMENT_SCAN_LIMIT = int(os.getenv("COMMENT_SCAN_LIMIT", "20"))
MAX_REPLY_PER_RUN = int(os.getenv("MAX_REPLY_PER_RUN", "5"))


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


def load_replied() -> Dict:
    default_data = {"comments": []}

    if not os.path.exists(REPLIED_FILE):
        return default_data

    try:
        with open(REPLIED_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        if not isinstance(raw, dict):
            return default_data

        raw.setdefault("comments", [])
        return raw
    except Exception:
        return default_data


def save_replied(data: Dict) -> None:
    with open(REPLIED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def mark_comment_replied(comment_id: str) -> None:
    data = load_replied()
    if comment_id not in data["comments"]:
        data["comments"].append(comment_id)
    save_replied(data)


def was_comment_replied(comment_id: str) -> bool:
    data = load_replied()
    return comment_id in data["comments"]


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


def to_float(v) -> float:
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def norm_text(v) -> str:
    return str(v or "").strip()


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


def create_real_short_link(long_url: str, slug: str) -> str:
    if not long_url:
        return ""

    if not SHORTENER_BASE_URL:
        return long_url

    base = SHORTENER_BASE_URL.rstrip("/")
    create_url = f"{base}/create?target={quote(long_url, safe='')}&slug={quote(slug, safe='')}"

    try:
        res = requests.get(create_url, timeout=20)

        if res.status_code == 200:
            data = res.json()
            if data.get("ok") and data.get("short_url"):
                return data["short_url"]

        if res.status_code == 409:
            return f"{base}/{slug}"

        print("SHORTENER ERROR:", res.status_code, res.text[:300], flush=True)
        return long_url
    except Exception as e:
        print("SHORTENER EXCEPTION:", e, flush=True)
        return long_url


def build_shopee_affiliate_link(row: Dict, page_mode: str) -> str:
    landing_page = norm_text(row.get("product_link"))
    itemid = norm_text(row.get("itemid"))

    if not landing_page or not itemid or not SHOPEE_AFFILIATE_ID:
        return ""

    encoded = quote(landing_page, safe="")
    sub_id = f"{SHOPEE_SUB_ID_PREFIX}-{page_mode}-{itemid}"

    return (
        f"https://s.shopee.co.th/an_redir?"
        f"origin_link={encoded}"
        f"&affiliate_id={SHOPEE_AFFILIATE_ID}"
        f"&sub_id={sub_id}"
    )


def has_link_data(row: Dict) -> bool:
    landing_page = norm_text(row.get("product_link"))
    itemid = norm_text(row.get("itemid"))
    return bool(landing_page and itemid and SHOPEE_AFFILIATE_ID)


def build_final_link(row: Dict, page_mode: str) -> tuple[str, str]:
    itemid = norm_text(row.get("itemid"))
    long_aff_link = build_shopee_affiliate_link(row, page_mode)

    if not long_aff_link:
        return "", "none"

    if SHORTENER_BASE_URL:
        slug = f"{page_mode}-{itemid}".lower()
        short_link = create_real_short_link(long_aff_link, slug)
        if short_link and short_link != long_aff_link:
            return short_link, "worker_short"
        if short_link:
            return short_link, "affiliate_long"

    return long_aff_link, "affiliate_long"


def is_ben_target(title: str, cat1: str, cat2: str, cat3: str) -> bool:
    text = f"{title} {cat1} {cat2} {cat3}".lower()

    allow_keywords = [
        "electrical", "electric", "ไฟฟ้า", "อุปกรณ์ไฟฟ้า",
        "ปลั๊ก", "ปลั๊กไฟ", "รางปลั๊ก", "ปลั๊กพ่วง", "เต้ารับ", "เต้าเสียบ",
        "power socket", "socket", "power strip", "extension", "extension cord",
        "สายไฟ", "cable", "wire", "usb", "usb-c", "lightning",
        "adapter", "charger", "fast charge", "gan", "power adapter",
        "converter", "transformer", "เบรกเกอร์", "breaker", "switch", "สวิตช์",
        "หลอดไฟ", "led", "โคมไฟ", "ไฟฉาย",
        "tools", "tool", "เครื่องมือ", "เครื่องมือช่าง",
        "drill", "สว่าน", "ไขควง", "คีม", "ประแจ", "ค้อน", "เลื่อย",
        "multimeter", "tester", "เทสเตอร์", "มิเตอร์ไฟ",
        "กาว", "กาวร้อน", "กาวแห้งเร็ว", "ซิลิโคน", "sealant",
        "ตะขอ", "พุก", "พุกตะกั่ว", "anchor", "น็อต", "สกรู", "ตะปู",
        "เทปพันสายไฟ", "insulation tape", "เคเบิ้ลไทร์", "cable tie",
        "filter", "air purifier filter"
    ]

    block_keywords = [
        "bra", "bra pad", "บรา", "บราทรง", "เสื้อใน", "ชั้นใน",
        "fashion", "beauty", "cosmetic", "skincare", "สบู่", "soap", "ครีม",
        "lip", "ลิป", "เสื้อ", "กางเกง", "รองเท้า", "กระเป๋า", "หมวก",
        "iphone", "ipad", "macbook", "airpods", "apple watch",
        "case", "เคส", "lens protection", "full lens", "watch strap",
        "smart home", "camera", "cctv", "ip camera", "security camera",
        "กล้อง", "กล้องติดรถ", "dash cam", "smart plug", "smart bulb",
        "smart switch", "router", "mesh", "wifi", "sensor", "doorbell",
        "robot vacuum", "หุ่นยนต์ดูดฝุ่น",
        "food", "อาหาร", "ขนม", "ของเล่น", "toy",
        "ผ้าใบ", "กันฝน", "tarp", "tarpaulin", "canvas", "cover", "คลุมรถ",
        "ที่นอน", "หมอน", "ผ้าห่ม", "ตกแต่งบ้าน", "ของแต่งบ้าน",
        "ถุง", "ซอง", "ฝากาว", "แพ็ก", "แพค", "บรรจุภัณฑ์", "สติ๊กเกอร์",
        "เทปใส", "ซองใส", "ถุงแก้ว", "opp", "packing", "package", "poly bag",
        "กระทะ", "หม้อ", "เครื่องครัว", "ครัว", "ทำอาหาร", "ทอด",
        "frying pan", "pan", "cookware", "kitchenware", "kitchen"
    ]

    if any(k in text for k in block_keywords):
        return False

    return any(k in text for k in allow_keywords)


def is_hard_block_for_ben(title: str, cat1: str, cat2: str, cat3: str) -> bool:
    text = f"{title} {cat1} {cat2} {cat3}".lower()
    hard_blocks = [
        "bra", "bra pad", "บรา", "บราทรง", "เสื้อใน", "ชั้นใน",
        "fashion", "beauty", "cosmetic", "skincare", "สบู่", "ครีม",
        "เสื้อ", "กางเกง", "รองเท้า", "กระเป๋า",
        "iphone case", "ipad case", "เคสมือถือ", "watch strap",
        "smart home", "camera", "cctv", "ip camera", "security camera",
        "กล้อง", "กล้องติดรถ", "dash cam", "smart plug", "smart bulb",
        "router", "mesh", "wifi", "sensor", "doorbell",
        "food", "อาหาร", "ขนม", "ของเล่น", "toy",
        "ผ้าใบ", "กันฝน", "ตัดเย็บ", "แฟชั่น",
        "ถุง", "ซอง", "ฝากาว", "แพ็ก", "แพค", "บรรจุภัณฑ์", "สติ๊กเกอร์",
        "เทปใส", "ซองใส", "ถุงแก้ว", "opp", "packing", "package", "poly bag",
        "กระทะ", "หม้อ", "เครื่องครัว", "ครัว", "ทำอาหาร", "ทอด",
        "frying pan", "pan", "cookware", "kitchenware", "kitchen"
    ]
    return any(k in text for k in hard_blocks)


def is_smarthome_target(title: str, cat1: str, cat2: str, cat3: str) -> bool:
    text = f"{title} {cat1} {cat2} {cat3}".lower()

    allow_keywords = [
        "smart", "smart home", "wifi", "camera", "cctv", "ip camera",
        "security camera", "กล้อง", "smart plug", "wifi plug",
        "ปลั๊กอัจฉริยะ", "smart bulb", "smart light", "robot vacuum",
        "หุ่นยนต์ดูดฝุ่น", "sensor", "doorbell", "router", "mesh",
        "smart switch", "lens protection", "camera lens", "full lens",
        "watch strap", "watch active", "redmi watch", "led", "ไฟ led",
        "air purifier", "purifier", "filter", "dash cam", "กล้องติดรถ"
    ]

    block_keywords = [
        "power socket", "รางปลั๊ก", "ปลั๊กพ่วง", "สายไฟ", "extension cord",
        "drill", "ไขควง", "สว่าน", "คีม", "tester", "multimeter",
        "beauty", "สบู่", "soap", "fashion", "เสื้อ", "รองเท้า",
        "food", "อาหาร", "ผ้าใบ", "กันฝน", "tarp", "tarpaulin", "canvas",
        "ถุง", "ซอง", "ฝากาว", "แพ็ก", "แพค", "บรรจุภัณฑ์",
        "กระทะ", "หม้อ", "เครื่องครัว", "ครัว", "ทำอาหาร",
        "frying pan", "pan", "cookware", "kitchenware", "kitchen"
    ]

    if any(k in text for k in block_keywords):
        return False

    return any(k in text for k in allow_keywords)


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
        "usb", "gan", "power bank", "adapter", "ปลั๊ก",
        "switch", "led", "พุก", "กาว", "ตะขอ", "filter"
    ]
    if any(k in title for k in hot_words):
        score += 35

    if page_mode == "smart" and any(k in title for k in ["camera", "smart", "wifi", "led", "filter"]):
        score += 25

    if page_mode == "ben" and any(k in title for k in ["ปลั๊ก", "adapter", "gan", "กาว", "พุก", "น็อต", "สกรู", "กาวร้อน"]):
        score += 25

    return score


def choose_product(page_mode: str) -> Optional[Dict]:
    posted = load_posted()
    page_history = posted[page_mode]

    best_row = None
    best_score = -1
    count = 0
    no_link_count = 0

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

            if not has_link_data(row):
                no_link_count += 1
                continue

            if rating < 4.0:
                continue
            if sold < 20:
                continue

            image_key = normalize_image_key(image)
            if is_duplicate(page_history, itemid, image_key, title):
                continue

            if page_mode == "ben":
                if is_hard_block_for_ben(title, cat1, cat2, cat3):
                    continue

                ben_required_keywords = [
                    "ปลั๊ก", "ปลั๊กไฟ", "รางปลั๊ก", "ปลั๊กพ่วง",
                    "สายไฟ", "สายชาร์จ", "charger", "adapter", "gan",
                    "ไฟฟ้า", "electrical", "breaker", "เบรกเกอร์", "switch", "สวิตช์",
                    "หลอดไฟ", "led", "โคมไฟ",
                    "เครื่องมือ", "tool", "drill", "สว่าน", "ไขควง", "คีม", "ประแจ",
                    "กาว", "พุก", "น็อต", "สกรู", "anchor", "เทปพันสายไฟ"
                ]

                raw_text = f"{title} {cat1} {cat2} {cat3}".lower()
                if not any(k in raw_text for k in ben_required_keywords):
                    continue

                if not is_ben_target(title, cat1, cat2, cat3):
                    continue
            else:
                if not is_smarthome_target(title, cat1, cat2, cat3):
                    continue

            score = score_product(row, page_mode)
            if score > best_score:
                best_score = score
                best_row = row

        except Exception:
            continue

    print(f"SCAN DONE ({page_mode}): {count}", flush=True)
    print(f"SKIP NO link ({page_mode}): {no_link_count}", flush=True)

    if not best_row:
        print("❌ No product found", flush=True)
        return None

    final_link, link_source = build_final_link(best_row, page_mode)

    product = {
        "itemid": norm_text(best_row.get("itemid")),
        "title": norm_text(best_row.get("title")),
        "image": norm_text(best_row.get("image_link")),
        "image_key": normalize_image_key(norm_text(best_row.get("image_link"))),
        "sold": to_float(best_row.get("item_sold")),
        "rating": to_float(best_row.get("item_rating")),
        "price": to_float(best_row.get("sale_price")),
        "link": final_link,
        "link_source": link_source,
        "cat1": norm_text(best_row.get("global_category1")),
        "cat2": norm_text(best_row.get("global_category2")),
        "cat3": norm_text(best_row.get("global_category3")),
    }

    print(
        f"✅ CHOSEN: {product['title']} | sold={product['sold']} | rating={product['rating']} | price={product['price']}",
        flush=True
    )
    print("LINK SOURCE:", product["link_source"], flush=True)
    print("FINAL LINK:", product["link"], flush=True)

    return product


def make_hook(page_mode: str) -> str:
    ben_hooks = [
        "⚡ ของแนวนี้กำลังขายดี กดดูตัวนี้ก่อน",
        "🔥 สายช่างและสายบ้านน่าดูตัวนี้มาก",
        "👀 รีวิวดี คนซื้อเยอะ ใช้งานจริง",
        "🛠 ของใช้คุ้ม ๆ ตัวนี้กำลังมาแรง",
    ]

    smart_hooks = [
        "📱 ของชิ้นนี้กำลังฮิต คนกดดูเยอะมาก",
        "🏠 ของแนว Smart Home ตัวนี้น่าสนใจมาก",
        "🔥 รีวิวพุ่ง คนซื้อเยอะ ใช้งานคุ้ม",
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
        "👉 กดดูรายละเอียดและราคาล่าสุดตรงนี้",
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
- ปิดท้ายให้คนกดลิงก์ด้านล่าง
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

        return f"{content}\n\n👉 กดดูรายละเอียดและราคาล่าสุดตรงนี้\n{product['link']}"
    except Exception as e:
        print("OPENAI ERROR:", e, flush=True)
        return fallback_caption(product, page_mode)


def get_page_posts(page_id: str, access_token: str, limit: int = 5) -> list:
    try:
        res = requests.get(
            f"https://graph.facebook.com/v25.0/{page_id}/posts",
            params={
                "access_token": access_token,
                "fields": "id,message,created_time",
                "limit": limit,
            },
            timeout=TIMEOUT,
        )
        data = res.json()
        return data.get("data", [])
    except Exception as e:
        print("GET PAGE POSTS ERROR:", e, flush=True)
        return []


def get_post_comments(post_id: str, access_token: str, limit: int = 20) -> list:
    try:
        res = requests.get(
            f"https://graph.facebook.com/v25.0/{post_id}/comments",
            params={
                "access_token": access_token,
                "fields": "id,message,from,created_time,parent",
                "filter": "stream",
                "limit": limit,
            },
            timeout=TIMEOUT,
        )
        data = res.json()
        return data.get("data", [])
    except Exception as e:
        print("GET COMMENTS ERROR:", e, flush=True)
        return []


def generate_comment_reply(comment_text: str, page_mode: str) -> str:
    fallback_map = {
        "ben": "ขอบคุณมากครับ สนใจรายละเอียดเพิ่มเติมกดลิงก์ใต้โพสต์ได้เลย 🙏",
        "smart": "ขอบคุณมากครับ ถ้าสนใจรายละเอียดเพิ่มเติมกดลิงก์ใต้โพสต์ได้เลย 🙏",
    }

    if not USE_OPENAI or not OPENAI_API_KEY:
        return fallback_map.get(page_mode, "ขอบคุณมากครับ 🙏")

    page_desc = "เพจเครื่องมือช่างและงานไฟฟ้า" if page_mode == "ben" else "เพจ Smart Home"

    prompt = f"""
คุณเป็นแอดมินเพจ {page_desc}
ช่วยตอบคอมเมนต์ลูกค้าแบบสั้น สุภาพ เป็นกันเอง ภาษาไทย

คอมเมนต์ลูกค้า:
{comment_text}

เงื่อนไข:
- ตอบสั้น 1-2 ประโยค
- สุภาพ
- ไม่เวอร์
- ไม่ใส่ราคา
- ไม่ใส่ข้อมูลที่ไม่รู้จริง
- ถ้าเป็นแนวสนใจซื้อ ให้ชวนกดลิงก์ใต้โพสต์
- ถ้าเป็นแนวชม ให้ขอบคุณ
- ถ้าเป็นแนวถามทั่วไป ให้ตอบกลาง ๆ และชวนดูรายละเอียดที่ลิงก์ใต้โพสต์
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
                    {"role": "system", "content": "คุณเป็นแอดมินเพจขายของ ตอบคอมเมนต์สั้น สุภาพ และน่าเชื่อถือ"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
            },
            timeout=45,
        )
        res.raise_for_status()
        data = res.json()
        content = data["choices"][0]["message"]["content"].strip()
        return content or fallback_map.get(page_mode, "ขอบคุณมากครับ 🙏")
    except Exception as e:
        print("OPENAI COMMENT REPLY ERROR:", e, flush=True)
        return fallback_map.get(page_mode, "ขอบคุณมากครับ 🙏")


def reply_to_comment(comment_id: str, access_token: str, message: str) -> bool:
    try:
        res = requests.post(
            f"https://graph.facebook.com/v25.0/{comment_id}/comments",
            data={
                "message": message,
                "access_token": access_token,
            },
            timeout=TIMEOUT,
        )
        data = res.json()
        print("REPLY COMMENT:", data, flush=True)
        return "id" in data
    except Exception as e:
        print("REPLY COMMENT ERROR:", e, flush=True)
        return False


def auto_reply_recent_comments(page_mode: str, page_id: str, access_token: str, page_name: str) -> None:
    if not AUTO_REPLY_COMMENTS:
        return

    posts = get_page_posts(page_id, access_token, limit=5)
    total_replied = 0

    for post in posts:
        post_id = norm_text(post.get("id"))
        if not post_id:
            continue

        comments = get_post_comments(post_id, access_token, COMMENT_SCAN_LIMIT)

        for c in comments:
            if total_replied >= MAX_REPLY_PER_RUN:
                break

            comment_id = norm_text(c.get("id"))
            message = norm_text(c.get("message"))
            from_obj = c.get("from") or {}
            from_name = norm_text(from_obj.get("name"))

            if not comment_id or not message:
                continue

            if was_comment_replied(comment_id):
                continue

            if from_name and from_name.lower() == page_name.lower():
                continue

            reply_text = generate_comment_reply(message, page_mode)
            ok = reply_to_comment(comment_id, access_token, reply_text)

            if ok:
                mark_comment_replied(comment_id)
                total_replied += 1
                time.sleep(2)

        if total_replied >= MAX_REPLY_PER_RUN:
            break

    print(f"AUTO REPLY DONE ({page_mode}): {total_replied}", flush=True)


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


def run_page(page_mode: str, page_id: str, access_token: str) -> None:
    if not page_id or not access_token:
        print(f"SKIP PAGE ({page_mode}) missing config", flush=True)
        return

    print("RUN PAGE:", page_mode, "***", flush=True)

    product = choose_product(page_mode)
    if product:
        print("IMAGE URL:", product["image"], flush=True)
        print("LINK:", product["link"], flush=True)

        caption = generate_caption(product, page_mode)
        post_id = post_image(page_id, access_token, product["image"], caption)

        if post_id:
            mark_as_posted(page_mode, product["itemid"], product["image_key"], product["title"])
            time.sleep(3)
            comment_link(post_id, access_token, product["link"])

    time.sleep(3)
    page_name = "BEN Home & Electrical" if page_mode == "ben" else "SmartHome Thailand"
    auto_reply_recent_comments(page_mode, page_id, access_token, page_name)


def run_all_pages() -> None:
    run_page("ben", PAGE_ID, PAGE_ACCESS_TOKEN)
    run_page("smart", PAGE_ID_2, PAGE_ACCESS_TOKEN_2)
