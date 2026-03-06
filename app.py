import os
import csv
import json
import random
import re
from urllib.parse import quote, urlparse

import requests
from openai import OpenAI


PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")
AFF_ID = os.getenv("SHOPEE_AFFILIATE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONTHLY_PROMO_TEXT = os.getenv("MONTHLY_PROMO_TEXT", "").strip()

STATE_FILE = "state.json"

MAX_ROWS = 800
TOP_POOL = 15
MAX_IMAGES_PER_POST = 1

HTTP_TIMEOUT = 20
OPENAI_TIMEOUT = 25

MIN_RATING = 4.0
MIN_SOLD = 10

ALLOWED_KEYWORDS = [
    "ปลั๊ก", "ปลั๊กไฟ", "สวิตช์", "เต้ารับ", "รางปลั๊ก",
    "สายไฟ", "สายไฟฟ้า", "คอนเนคเตอร์", "เทอร์มินอล", "dc jack",
    "หลอดไฟ", "โคมไฟ", "ไฟ led", "led", "lamp", "light", "bulb",
    "breaker", "relay", "adapter", "ups", "solar", "inverter",
    "plug", "socket", "switch", "wire", "cable", "connector", "terminal",
    "ไขควง", "คีม", "สว่าน", "multimeter", "tester", "tool",
    "พัดลม", "หม้อแปลง", "อะแดปเตอร์", "สปอตไลท์", "ไฟเส้น", "ไฟโซล่า"
]

BLOCK_KEYWORDS = [
    "เสื้อ", "กางเกง", "รองเท้า", "กระเป๋า", "ลิป", "ครีม", "เซรั่ม",
    "shirt", "pants", "shoes", "bag", "cosmetic", "toy", "food", "snack"
]

CATEGORY_RULES = {
    "ปลั๊กและสวิตช์": ["ปลั๊ก", "ปลั๊กไฟ", "สวิตช์", "เต้ารับ", "รางปลั๊ก", "plug", "socket", "switch"],
    "สายไฟและอุปกรณ์เดินสาย": ["สายไฟ", "คอนเนคเตอร์", "เทอร์มินอล", "wire", "cable", "connector", "terminal", "dc jack"],
    "หลอดไฟและโคมไฟ": ["หลอด", "โคม", "led", "lamp", "light", "bulb", "สปอตไลท์", "ไฟเส้น"],
    "เครื่องมือช่างไฟ": ["ไขควง", "คีม", "สว่าน", "multimeter", "tester", "tool"],
    "อุปกรณ์ไฟฟ้าในบ้าน": ["breaker", "relay", "adapter", "ups", "solar", "inverter", "พัดลม", "หม้อแปลง"]
}

CATEGORY_HASHTAGS = {
    "ปลั๊กและสวิตช์": "#ปลั๊กไฟ #สวิตช์ไฟ #อุปกรณ์ไฟฟ้า",
    "สายไฟและอุปกรณ์เดินสาย": "#สายไฟ #อุปกรณ์เดินสาย #งานไฟ",
    "หลอดไฟและโคมไฟ": "#หลอดไฟ #โคมไฟ #ไฟLED",
    "เครื่องมือช่างไฟ": "#เครื่องมือช่าง #ช่างไฟ #งานซ่อมบ้าน",
    "อุปกรณ์ไฟฟ้าในบ้าน": "#อุปกรณ์ไฟฟ้าในบ้าน #ของใช้ไฟฟ้า #ติดบ้านไว้",
    "ทั่วไป": "#อุปกรณ์ไฟฟ้า #ของใช้ในบ้าน #BENHomeElectrical"
}


def log(msg):
    print(msg, flush=True)


def validate_env():
    missing = []
    for key, value in {
        "PAGE_ID": PAGE_ID,
        "PAGE_ACCESS_TOKEN": TOKEN,
        "SHOPEE_CSV_URL": CSV_URL,
        "SHOPEE_AFFILIATE_ID": AFF_ID,
        "OPENAI_API_KEY": OPENAI_API_KEY,
    }.items():
        if not value:
            missing.append(key)

    if missing:
        raise ValueError("Missing env vars: " + ", ".join(missing))


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"posted_links": [], "history": []}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("posted_links", [])
        data.setdefault("history", [])
        return data
    except Exception:
        return {"posted_links": [], "history": []}


def save_state(state):
    state["posted_links"] = state["posted_links"][-500:]
    state["history"] = state["history"][-200:]

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def pick_first_nonempty(row, keys):
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


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
    return " ".join((name or "").lower().split())


def detect_category(name):
    n = normalize_name(name)
    best_category = "ทั่วไป"
    best_score = 0

    for category, keywords in CATEGORY_RULES.items():
        score = sum(1 for kw in keywords if kw.lower() in n)
        if score > best_score:
            best_score = score
            best_category = category

    return best_category, best_score


def allow_product(name):
    n = normalize_name(name)

    if any(bad in n for bad in BLOCK_KEYWORDS):
        return False

    return any(kw in n for kw in ALLOWED_KEYWORDS)


def is_affiliate_link(link: str) -> bool:
    if not link:
        return False
    link = str(link).strip().lower()
    return "affiliate_id=" in link and "an_redir" in link


def is_short_shopee_link(link: str) -> bool:
    if not link:
        return False
    host = urlparse(str(link).strip()).netloc.lower()
    return "shopee.ee" in host


def make_aff_link_from_product_link(product_link: str) -> str:
    if not product_link:
        return ""

    product_link = str(product_link).strip()

    if is_affiliate_link(product_link):
        return product_link

    if is_short_shopee_link(product_link):
        return product_link

    return f"https://shopee.ee/an_redir?affiliate_id={AFF_ID}&origin_link={quote(product_link, safe='')}"


def get_monthly_promo():
    if MONTHLY_PROMO_TEXT:
        return MONTHLY_PROMO_TEXT
    return "🔥 โปรประจำเดือน: กดเช็กราคาล่าสุด / ดูส่วนลด / เช็กโปรส่งฟรีก่อนสั่งซื้อ"


def extract_promo_info(row):
    discount = safe_float(
        pick_first_nonempty(row, [
            "discount_percentage", "discount", "discount_percent"
        ]),
        0
    )

    sale_price = safe_float(
        pick_first_nonempty(row, [
            "sale_price", "item_price", "model_price", "model_prices"
        ]),
        0
    )

    original_price = safe_float(
        pick_first_nonempty(row, [
            "price", "original_price", "item_original_price"
        ]),
        0
    )

    has_promo = False
    if discount > 0:
        has_promo = True
    elif original_price > 0 and sale_price > 0 and sale_price < original_price:
        has_promo = True

    return {
        "has_promo": has_promo,
        "discount_percentage": discount,
        "sale_price_num": sale_price,
        "original_price_num": original_price,
    }


def read_products():
    log("STEP 1: download csv")

    r = requests.get(CSV_URL, timeout=HTTP_TIMEOUT, stream=True)
    r.raise_for_status()

    lines = (
        line.decode("utf-8-sig", errors="ignore")
        for line in r.iter_lines()
        if line
    )
    reader = csv.DictReader(lines)

    products = []

    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            break

        if i == 0:
            log(f"CSV fields: {list(row.keys())}")

        name = pick_first_nonempty(row, [
            "product_name", "name", "title", "item_name", "product title", "model_names"
        ])
        product_link = pick_first_nonempty(row, [
            "product_link", "link", "item_link", "url"
        ])

        rating = safe_float(pick_first_nonempty(row, [
            "item_rating", "rating", "avg_rating", "shop_rating"
        ]), 0)

        sold = safe_int(pick_first_nonempty(row, [
            "historical_sold", "sold", "sales"
        ]), 0)

        original_price = pick_first_nonempty(row, [
            "price", "original_price", "item_original_price"
        ])
        sale_price = pick_first_nonempty(row, [
            "sale_price", "item_price", "model_price", "model_prices"
        ])

        img1 = pick_first_nonempty(row, ["image_link", "image", "main_image", "image_url", "additional_image_link"])
        img2 = pick_first_nonempty(row, ["image_link_2", "image_2", "image2", "image_link_3"])
        img3 = pick_first_nonempty(row, ["image_link_4", "image_3", "image3", "image_link_5"])

        if not name or not product_link or not img1:
            continue

        if not allow_product(name):
            continue

        if rating < MIN_RATING:
            continue

        if sold < MIN_SOLD:
            continue

        promo_info = extract_promo_info(row)
        price_num = safe_float(sale_price or original_price, 0)
        if price_num <= 0:
            continue

        category, category_score = detect_category(name)
        images = [x for x in [img1, img2, img3] if x]

        products.append({
            "name": name[:120],
            "product_link": product_link,
            "aff_link": make_aff_link_from_product_link(product_link),
            "price": str(sale_price or original_price).strip(),
            "original_price": str(original_price).strip(),
            "sale_price": str(sale_price).strip(),
            "price_num": price_num,
            "rating": rating,
            "sold": sold,
            "has_promo": promo_info["has_promo"],
            "discount_percentage": promo_info["discount_percentage"],
            "category": category,
            "category_score": category_score,
            "images": images[:MAX_IMAGES_PER_POST]
        })

    log(f"STEP 2: valid products = {len(products)}")
    return products


def local_score(p):
    score = 0
    score += p["rating"] * 45
    score += p["sold"] * 0.7
    score += p["category_score"] * 12
    score += p.get("discount_percentage", 0) * 3

    if p["has_promo"]:
        score += 20

    if p["price_num"] <= 99:
        score += 20
    elif p["price_num"] <= 299:
        score += 16
    elif p["price_num"] <= 699:
        score += 10

    score += random.random() * 3
    return score


def build_candidate_pool(products, posted_links):
    fresh = [p for p in products if p["product_link"] not in posted_links]
    base_pool = fresh or products

    promo_pool = [p for p in base_pool if p["has_promo"]]

    if promo_pool:
        chosen_pool = sorted(promo_pool, key=local_score, reverse=True)[:TOP_POOL]
        log(f"STEP 3: using promo pool = {len(chosen_pool)}")
        return chosen_pool

    chosen_pool = sorted(base_pool, key=local_score, reverse=True)[:TOP_POOL]
    log(f"STEP 3: no promo items, fallback pool = {len(chosen_pool)}")
    return chosen_pool


def ai_select_product(products):
    client = OpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_TIMEOUT)

    compact = []
    for idx, p in enumerate(products):
        compact.append({
            "index": idx,
            "name": p["name"],
            "category": p["category"],
            "category_score": p["category_score"],
            "price": p["price"],
            "original_price": p.get("original_price", ""),
            "sale_price": p.get("sale_price", ""),
            "has_promo": p.get("has_promo", False),
            "discount_percentage": p.get("discount_percentage", 0),
            "rating": p["rating"],
            "sold": p["sold"],
        })

    prompt = f"""
คุณเป็น AI ผู้ช่วยคัดสินค้าสำหรับเพจ Facebook ชื่อ BEN Home & Electrical

หน้าที่:
เลือกสินค้าเพียง 1 ชิ้นจากรายการด้านล่าง เพื่อเอาไปโพสต์ขาย

หลักการ:
- ต้องตรงหมวดเพจที่สุด
- ต้องเป็นแนวอุปกรณ์ไฟฟ้า ของใช้ไฟฟ้า งานช่างไฟ ของใช้ในบ้าน
- rating สูงดีกว่า
- sold สูงดีกว่า
- ถ้ามีโปร / ลดราคา / sale price ให้ความสำคัญเพิ่ม
- ถ้าไม่มีสินค้าโปร ให้เลือกตัวที่ตรงเพจและขายง่ายที่สุด
- เลือกตัวที่คนทั่วไปน่าจะซื้อได้ง่าย

ตอบเป็นเลข index อย่างเดียว ห้ามมีคำอื่น

รายการสินค้า:
{json.dumps(compact, ensure_ascii=False)}
"""

    try:
        r = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )
        text = (r.output_text or "").strip()
        idx = int(re.sub(r"[^\d]", "", text) or "0")
        if 0 <= idx < len(products):
            return products[idx]
    except Exception as e:
        log(f"AI select failed: {e}")

    return sorted(products, key=local_score, reverse=True)[0]


def ai_generate_caption(product):
    client = OpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_TIMEOUT)

    hashtags = CATEGORY_HASHTAGS.get(product["category"], CATEGORY_HASHTAGS["ทั่วไป"])
    promo = get_monthly_promo()

    prompt = f"""
เขียน caption Facebook ภาษาไทย สำหรับเพจ BEN Home & Electrical

สินค้า:
ชื่อ: {product["name"]}
หมวด: {product["category"]}
ราคาปัจจุบัน: {product["price"]} บาท
ราคาเดิม: {product.get("original_price", "")}
เรตติ้ง: {product["rating"]}
ยอดขาย: {product["sold"]}
มีโปร: {product.get("has_promo", False)}
ส่วนลด: {product.get("discount_percentage", 0)}%

เงื่อนไข:
- โทนขายของจริง อ่านง่าย
- มี emoji พอประมาณ
- บอกว่าสินค้านี้ตรงหมวดกับเพจ
- ถ้ามีโปรให้ชูจุดคุ้มค่า
- ถ้าไม่มีโปร ให้เน้นรีวิวดีและยอดขายดี
- ไม่เกิน 8 บรรทัดก่อนลิงก์
- ห้ามพูดเกินจริง
- บรรทัดสุดท้ายก่อนลิงก์ให้เป็น "🛒 สั่งซื้อสินค้า"
- ไม่ต้องใส่ลิงก์ในคำตอบ
- ใส่ข้อความโปรนี้แบบเนียน ๆ: {promo}
"""

    try:
        r = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )
        text = (r.output_text or "").strip()
        if text:
            return f"{text}\n{product['aff_link']}\n\n#BENHomeElectrical #ShopeeAffiliate {hashtags}"
    except Exception as e:
        log(f"AI caption failed: {e}")

    return (
        f"⭐ รีวิวดี คนซื้อเยอะ\n\n"
        f"{product['name']}\n"
        f"💰 ราคา {product['price']} บาท\n"
        f"⭐ รีวิว {product['rating']:.1f}/5\n"
        f"📦 ขายแล้ว {product['sold']}\n"
        f"{get_monthly_promo()}\n"
        f"🛒 สั่งซื้อสินค้า\n"
        f"{product['aff_link']}\n\n"
        f"#BENHomeElectrical #ShopeeAffiliate {hashtags}"
    )


def graph_post(endpoint, payload):
    r = requests.post(endpoint, data=payload, timeout=HTTP_TIMEOUT)
    try:
        return r.json()
    except Exception:
        return {"error": {"message": r.text[:300]}}


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
        return None

    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    payload = {
        "message": caption_text,
        "link": product["aff_link"],
        "access_token": TOKEN
    }

    for i, media_id in enumerate(media_ids):
        payload[f'attached_media[{i}]'] = f'{{"media_fbid":"{media_id}"}}'

    log("STEP 5: create post")
    data = graph_post(endpoint, payload)
    if "id" not in data:
        log(f"post failed: {data}")
        return None
    return data["id"]


def comment_link(post_id, product):
    endpoint = f"https://graph.facebook.com/v25.0/{post_id}/comments"
    payload = {
        "message": product["aff_link"],
        "access_token": TOKEN
    }
    try:
        data = graph_post(endpoint, payload)
        log(f"comment result: {data}")
    except Exception as e:
        log(f"comment failed: {e}")


def main():
    log("START APP")
    validate_env()

    state = load_state()
    products = read_products()
    if not products:
        log("No products found")
        return

    candidate_pool = build_candidate_pool(products, set(state["posted_links"]))
    product = ai_select_product(candidate_pool)

    log(f"STEP 3A: chosen = {product['name']}")
    log(f"STEP 3B: category = {product['category']}")
    log(f"STEP 3C: rating = {product['rating']}, sold = {product['sold']}, promo = {product['has_promo']}")

    caption_text = ai_generate_caption(product)
    post_id = post_product(product, caption_text)

    if post_id:
        log(f"post created: {post_id}")
        comment_link(post_id, product)

        state["posted_links"].append(product["product_link"])
        state["history"].append({
            "name": product["name"],
            "product_link": product["product_link"],
            "aff_link": product["aff_link"],
            "post_id": post_id
        })
        save_state(state)
    else:
        log("Post failed")


if __name__ == "__main__":
    main()
