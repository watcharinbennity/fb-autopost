import os
import csv
import json
import random
import re
import time
from urllib.parse import quote

import requests


PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")
AFF_ID = os.getenv("SHOPEE_AFFILIATE_ID")
MONTHLY_PROMO_TEXT = os.getenv("MONTHLY_PROMO_TEXT", "").strip()

STATE_FILE = "state.json"

MAX_ROWS = 800
TOP_POOL = 30
MAX_IMAGES_PER_POST = 1

# ผ่อนเงื่อนไขก่อน เพื่อให้มีสินค้าผ่าน
MIN_RATING = 0
MIN_SOLD = 0

HTTP_TIMEOUT = 25
RETRY_COUNT = 2
RETRY_SLEEP = 2

ALLOWED_KEYWORDS = [
    # ไทย
    "ปลั๊ก", "ปลั๊กไฟ", "รางปลั๊ก", "เต้ารับ", "สวิตช์", "สวิตช์ไฟ",
    "สายไฟ", "สายไฟฟ้า", "เทปพันสายไฟ", "หางปลา", "คอนเนคเตอร์",
    "หลอดไฟ", "หลอด led", "โคมไฟ", "ไฟ led", "สปอตไลท์",
    "ไขควง", "ไขควงเช็คไฟ", "คีม", "สว่าน", "มัลติมิเตอร์", "มิเตอร์",
    "เบรกเกอร์", "ตู้ไฟ", "รีเลย์", "โซล่า", "อินเวอร์เตอร์", "แบตเตอรี่", "แบต",

    # อังกฤษ
    "plug", "socket", "power strip", "extension", "outlet",
    "wire", "cable", "connector", "terminal",
    "led", "lamp", "light", "bulb", "spotlight",
    "screwdriver", "pliers", "drill", "multimeter", "tester",
    "breaker", "relay", "switch", "ups", "inverter", "solar", "battery"
]

BLOCK_KEYWORDS = [
    "เสื้อ", "กางเกง", "รองเท้า", "กระเป๋า", "ลิป", "ครีม", "เซรั่ม",
    "ตุ๊กตา", "ของเล่น", "อาหาร", "ขนม", "น้ำหอม", "เครื่องสำอาง",
    "เคสมือถือ", "ฟิล์ม", "สร้อย", "แหวน", "หมวก", "นาฬิกา",
    "shirt", "pants", "shoes", "bag", "lipstick", "cream", "toy", "food", "snack"
]

CATEGORY_RULES = {
    "ปลั๊กและสวิตช์": [
        "ปลั๊ก", "ปลั๊กไฟ", "รางปลั๊ก", "เต้ารับ", "สวิตช์", "สวิตช์ไฟ",
        "plug", "socket", "power strip", "extension", "outlet", "switch"
    ],
    "สายไฟและอุปกรณ์เดินสาย": [
        "สายไฟ", "สายไฟฟ้า", "เทปพันสายไฟ", "หางปลา", "คอนเนคเตอร์", "วายนัท",
        "wire", "cable", "connector", "terminal"
    ],
    "หลอดไฟและโคมไฟ": [
        "หลอดไฟ", "หลอด led", "โคมไฟ", "ไฟ led", "ไฟเส้น", "สปอตไลท์",
        "led", "lamp", "light", "bulb", "spotlight"
    ],
    "เครื่องมือช่างไฟ": [
        "ไขควง", "ไขควงเช็คไฟ", "คีม", "สว่าน", "มัลติมิเตอร์", "มิเตอร์", "เครื่องมือ",
        "screwdriver", "pliers", "drill", "multimeter", "tester", "tool"
    ],
    "โซล่าและพลังงานสำรอง": [
        "โซล่า", "solar", "ups", "อินเวอร์เตอร์", "inverter", "แบตเตอรี่", "battery", "แบต"
    ],
    "อุปกรณ์ไฟฟ้าในบ้าน": [
        "เบรกเกอร์", "ตู้ไฟ", "รีเลย์", "อุปกรณ์ไฟฟ้า", "พัดลม", "อะแดปเตอร์",
        "breaker", "relay", "adapter", "fan"
    ]
}

CATEGORY_HASHTAGS = {
    "ปลั๊กและสวิตช์": "#ปลั๊กไฟ #สวิตช์ไฟ #อุปกรณ์ไฟฟ้า",
    "สายไฟและอุปกรณ์เดินสาย": "#สายไฟ #อุปกรณ์เดินสาย #งานไฟ",
    "หลอดไฟและโคมไฟ": "#หลอดไฟ #โคมไฟ #ไฟLED",
    "เครื่องมือช่างไฟ": "#เครื่องมือช่าง #ช่างไฟ #งานซ่อมบ้าน",
    "โซล่าและพลังงานสำรอง": "#โซล่า #UPS #พลังงานสำรอง",
    "อุปกรณ์ไฟฟ้าในบ้าน": "#อุปกรณ์ไฟฟ้าในบ้าน #ของใช้ไฟฟ้า #ติดบ้านไว้",
    "ทั่วไป": "#อุปกรณ์ไฟฟ้า #ของใช้ในบ้าน #BENHomeElectrical"
}

STYLE_OPENERS = {
    "problem": [
        "⚡ บ้านไหนกำลังหาอุปกรณ์แนวนี้ ลองดูตัวนี้",
        "🏠 ของใช้งานจริงที่ควรมีติดบ้าน",
        "🛠️ ถ้ากำลังซ่อมหรือแต่งระบบไฟ ลองดูตัวนี้"
    ],
    "selling": [
        "🔥 ตัวนี้ขายดีใน Shopee",
        "⭐ รีวิวดี คนซื้อเยอะ",
        "💥 ของใช้แนว Home & Electrical ที่น่าสนใจ"
    ],
    "review": [
        "✨ ดูจากรีวิวและยอดขายแล้ว น่าใช้มาก",
        "📌 ตัวนี้น่าสนใจสำหรับคนหาของใช้แนวไฟฟ้า",
        "⚡ ของดีที่อยากเอามาแนะนำ"
    ]
}

CTA_LINES = [
    "กดดูรายละเอียด / เช็กราคาล่าสุด:",
    "สนใจกดดูที่ลิงก์นี้:",
    "เช็กราคา / โปรล่าสุดได้ที่:",
    "กดดูสินค้าได้เลย:"
]


def log(message):
    print(message, flush=True)


def validate_env():
    missing = []
    if not PAGE_ID:
        missing.append("PAGE_ID")
    if not TOKEN:
        missing.append("PAGE_ACCESS_TOKEN")
    if not CSV_URL:
        missing.append("SHOPEE_CSV_URL")
    if missing:
        raise ValueError("Missing env vars: " + ", ".join(missing))


def request_with_retry(method, url, **kwargs):
    last_error = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            return requests.request(method, url, timeout=HTTP_TIMEOUT, **kwargs)
        except Exception as e:
            last_error = e
            log(f"request failed attempt {attempt}/{RETRY_COUNT}: {e}")
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_SLEEP)
    raise last_error


def safe_float(value, default=0.0):
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return default


def normalize_name(name):
    name = (name or "").strip().lower()
    name = re.sub(r"\s+", " ", name)
    return name


def build_token_key(name):
    name = normalize_name(name)
    name = re.sub(r"[^0-9a-zA-Zก-๙\s]", " ", name)
    parts = [x for x in name.split() if len(x) >= 2]
    return "|".join(sorted(set(parts[:5])))


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "posted_links": [],
            "posted_names": [],
            "posted_tokens": [],
            "posted_categories": [],
            "history": []
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("posted_links", [])
        data.setdefault("posted_names", [])
        data.setdefault("posted_tokens", [])
        data.setdefault("posted_categories", [])
        data.setdefault("history", [])
        return data
    except Exception as e:
        log(f"load_state error: {e}")
        return {
            "posted_links": [],
            "posted_names": [],
            "posted_tokens": [],
            "posted_categories": [],
            "history": []
        }


def save_state(state):
    state["posted_links"] = state["posted_links"][-500:]
    state["posted_names"] = state["posted_names"][-500:]
    state["posted_tokens"] = state["posted_tokens"][-500:]
    state["posted_categories"] = state["posted_categories"][-50:]
    state["history"] = state["history"][-100:]

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def detect_category(name):
    n = normalize_name(name)

    best_category = "ทั่วไป"
    best_score = 0

    for category, keywords in CATEGORY_RULES.items():
        score = 0
        for kw in keywords:
            if kw.lower() in n:
                score += 1
        if score > best_score:
            best_score = score
            best_category = category

    return best_category, best_score


def allow_product(name):
    n = normalize_name(name)

    for bad in BLOCK_KEYWORDS:
        if bad.lower() in n:
            return False, "ทั่วไป", 0

    matched = any(k.lower() in n for k in ALLOWED_KEYWORDS)
    category, category_score = detect_category(name)

    if not matched:
        return False, category, category_score

    return True, category, category_score


def make_aff_link(link):
    if not AFF_ID:
        return link
    return f"https://shopee.ee/an_redir?affiliate_id={AFF_ID}&origin_link={quote(link, safe='')}"


def get_monthly_promo():
    if MONTHLY_PROMO_TEXT:
        return MONTHLY_PROMO_TEXT
    return "🔥 โปรประจำเดือน: กดเช็กราคาล่าสุด / โค้ดส่วนลด / โปรส่งฟรีก่อนสั่งซื้อ"


def choose_style():
    return random.choice(["problem", "selling", "review"])


def pick_first_nonempty(row, keys):
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def read_products():
    log("STEP 1: download csv")

    response = request_with_retry("GET", CSV_URL, stream=True)
    response.raise_for_status()

    lines = (
        line.decode("utf-8-sig", errors="ignore")
        for line in response.iter_lines()
        if line
    )
    reader = csv.DictReader(lines)

    products = []

    for i, row in enumerate(reader):
        if i == 0:
            log(f"CSV fields: {list(row.keys())}")

        if i >= MAX_ROWS:
            break

        name = pick_first_nonempty(row, [
            "product_name", "name", "title", "item_name", "product title"
        ])
        price = pick_first_nonempty(row, [
            "price", "sale_price", "item_price"
        ])
        link = pick_first_nonempty(row, [
            "product_link", "link", "item_link", "url"
        ])
        rating_raw = pick_first_nonempty(row, [
            "item_rating", "rating", "avg_rating"
        ])
        sold_raw = pick_first_nonempty(row, [
            "historical_sold", "sold", "sales"
        ])

        img1 = pick_first_nonempty(row, [
            "image_link", "image", "main_image", "image_url"
        ])
        img2 = pick_first_nonempty(row, [
            "image_link_2", "image_2", "image2"
        ])
        img3 = pick_first_nonempty(row, [
            "image_link_3", "image_3", "image3"
        ])

        rating = safe_float(rating_raw, 0)
        sold = safe_int(sold_raw, 0)

        if not name or not link or not img1:
            continue

        is_allowed, category, category_score = allow_product(name)
        if not is_allowed:
            continue

        if rating < MIN_RATING or sold < MIN_SOLD:
            continue

        price_num = safe_float(price, 0)
        if price_num <= 0:
            continue

        images = [x for x in [img1, img2, img3] if x]

        products.append({
            "name": name[:110],
            "name_key": normalize_name(name),
            "token_key": build_token_key(name),
            "category": category,
            "category_score": category_score,
            "price": str(price).strip(),
            "price_num": price_num,
            "link": link,
            "rating": rating,
            "sold": sold,
            "images": images[:MAX_IMAGES_PER_POST]
        })

    log(f"STEP 2: valid products = {len(products)}")
    return products


def recent_category_penalty(category, state):
    recent = state.get("posted_categories", [])[-3:]
    if not recent:
        return 0

    penalty = 0
    if recent and recent[-1] == category:
        penalty += 10

    same_count = sum(1 for c in recent if c == category)
    if same_count >= 2:
        penalty += 10

    return penalty


def score_product(product, state):
    score = 0.0
    score += product["rating"] * 40
    score += product["sold"] * 0.45
    score += product["category_score"] * 10

    if product["price_num"] <= 99:
        score += 20
    elif product["price_num"] <= 299:
        score += 15
    elif product["price_num"] <= 699:
        score += 8
    else:
        score += 3

    if product["category"] in [
        "ปลั๊กและสวิตช์",
        "สายไฟและอุปกรณ์เดินสาย",
        "หลอดไฟและโคมไฟ",
        "เครื่องมือช่างไฟ"
    ]:
        score += 10

    score -= recent_category_penalty(product["category"], state)
    score += random.random() * 3
    return score


def choose_product(products, state):
    if not products:
        return None

    posted_links = set(state.get("posted_links", []))
    posted_names = set(state.get("posted_names", []))
    posted_tokens = set(state.get("posted_tokens", []))

    fresh = [
        p for p in products
        if p["link"] not in posted_links
        and p["name_key"] not in posted_names
        and p["token_key"] not in posted_tokens
    ]

    pool = fresh if fresh else products
    ranked = sorted(pool, key=lambda x: score_product(x, state), reverse=True)[:TOP_POOL]
    chosen = ranked[0] if ranked else None

    if chosen:
        log(f"STEP 3: chosen = {chosen['name']} | category = {chosen['category']}")

    return chosen


def build_caption(product, style):
    opener = random.choice(STYLE_OPENERS[style])
    cta = random.choice(CTA_LINES)
    hashtags = CATEGORY_HASHTAGS.get(product["category"], CATEGORY_HASHTAGS["ทั่วไป"])
    promo = get_monthly_promo()

    return (
        f"{opener}\n\n"
        f"{product['name']}\n\n"
        f"หมวด: {product['category']}\n"
        f"💰 ราคา {product['price']} บาท\n"
        f"⭐ รีวิว {product['rating']:.1f}/5\n"
        f"📦 ขายแล้ว {product['sold']}\n"
        f"{promo}\n\n"
        f"{cta}\n"
        f"{make_aff_link(product['link'])}\n\n"
        f"#BENHomeElectrical #ShopeeAffiliate {hashtags}"
    )


def graph_post(endpoint, payload):
    response = request_with_retry("POST", endpoint, data=payload)
    try:
        return response.json()
    except Exception:
        return {"error": {"message": response.text[:300]}}


def upload_photo(url):
    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"
    payload = {
        "url": url,
        "published": "false",
        "access_token": TOKEN
    }

    data = graph_post(endpoint, payload)
    if "id" not in data:
        raise RuntimeError(f"upload_photo failed: {data}")
    return data["id"]


def post_product(product, caption_text):
    log("STEP 4: upload image")

    media_ids = []
    for image_url in product["images"]:
        try:
            media_id = upload_photo(image_url)
            media_ids.append(media_id)
            log(f"uploaded image id = {media_id}")
        except Exception as e:
            log(f"upload failed: {e}")

    if not media_ids:
        log("no uploaded images")
        return None

    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    payload = {
        "message": caption_text,
        "access_token": TOKEN
    }

    for i, media_id in enumerate(media_ids):
        payload[f"attached_media[{i}]"] = f'{{"media_fbid":"{media_id}"}}'

    log("STEP 5: create post")
    data = graph_post(endpoint, payload)

    if "id" not in data:
        log(f"post failed: {data}")
        return None

    return data["id"]


def comment_link(post_id, product):
    endpoint = f"https://graph.facebook.com/v25.0/{post_id}/comments"
    payload = {
        "message": (
            f"{get_monthly_promo()}\n\n"
            f"สนใจตัวนี้กดลิงก์ได้เลย 👇\n"
            f"{make_aff_link(product['link'])}\n\n"
            f"✅ เช็กราคาล่าสุด\n"
            f"✅ ดูรีวิวเพิ่ม\n"
            f"✅ ดูโปรในร้าน"
        ),
        "access_token": TOKEN
    }

    try:
        data = graph_post(endpoint, payload)
        log(f"comment result: {data}")
    except Exception as e:
        log(f"comment failed: {e}")


def update_state_after_post(state, product, post_id, style):
    state["posted_links"].append(product["link"])
    state["posted_names"].append(product["name_key"])
    state["posted_tokens"].append(product["token_key"])
    state["posted_categories"].append(product["category"])
    state["history"].append({
        "name": product["name"],
        "category": product["category"],
        "style": style,
        "link": product["link"],
        "post_id": post_id
    })


def main():
    log("START APP")
    validate_env()

    state = load_state()
    products = read_products()

    if not products:
        log("No products found")
        return

    product = choose_product(products, state)
    if not product:
        log("No product selected")
        return

    style = choose_style()
    log(f"STEP 3A: style = {style}")

    caption_text = build_caption(product, style)
    post_id = post_product(product, caption_text)

    if post_id:
        log(f"post created: {post_id}")
        comment_link(post_id, product)
        update_state_after_post(state, product, post_id, style)
        save_state(state)
    else:
        log("Post failed")


if __name__ == "__main__":
    main()
