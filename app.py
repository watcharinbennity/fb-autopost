import os
import json
import random
import requests
from urllib.parse import quote
from openai import OpenAI


PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
AFF_ID = os.getenv("SHOPEE_AFFILIATE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONTHLY_PROMO_TEXT = os.getenv("MONTHLY_PROMO_TEXT", "").strip()

STATE_FILE = "state.json"

HTTP_TIMEOUT = 20
OPENAI_TIMEOUT = 25

LIMIT_API = 60
TOP_POOL = 12
MAX_IMAGES_PER_POST = 1

MIN_RATING = 4.5
MIN_SOLD = 100

# หมวดเพจ BEN Home & Electrical
ALLOWED_KEYWORDS = [
    "ปลั๊ก", "ปลั๊กไฟ", "สวิตช์", "เต้ารับ", "รางปลั๊ก",
    "สายไฟ", "สายไฟฟ้า", "คอนเนคเตอร์", "เทอร์มินอล",
    "หลอดไฟ", "โคมไฟ", "ไฟ led", "led", "lamp", "light", "bulb",
    "breaker", "relay", "adapter", "ups", "solar", "inverter",
    "plug", "socket", "switch", "wire", "cable", "connector", "terminal",
    "ไขควง", "คีม", "สว่าน", "multimeter", "tester", "tool",
    "พัดลม", "หม้อแปลง", "อะแดปเตอร์", "สปอตไลท์", "ไฟเส้น", "ไฟโซล่า",
    "ไฟประดับ", "ไฟกระพริบ", "โคม", "โซล่าเซลล์"
]

BLOCK_KEYWORDS = [
    "เสื้อ", "กางเกง", "รองเท้า", "กระเป๋า", "ลิป", "ครีม", "เซรั่ม",
    "shirt", "pants", "shoes", "bag", "cosmetic", "toy", "food", "snack"
]

CATEGORY_RULES = {
    "ปลั๊กและสวิตช์": ["ปลั๊ก", "ปลั๊กไฟ", "สวิตช์", "เต้ารับ", "รางปลั๊ก", "plug", "socket", "switch"],
    "สายไฟและอุปกรณ์เดินสาย": ["สายไฟ", "คอนเนคเตอร์", "เทอร์มินอล", "wire", "cable", "connector", "terminal"],
    "หลอดไฟและโคมไฟ": ["หลอด", "โคม", "led", "lamp", "light", "bulb", "สปอตไลท์", "ไฟเส้น", "ไฟประดับ"],
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


def normalize_name(name):
    return " ".join((name or "").lower().split())


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


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


def make_aff_link(product_link: str) -> str:
    if not product_link:
        return ""
    return f"https://shopee.ee/an_redir?affiliate_id={AFF_ID}&origin_link={quote(product_link, safe='')}"


def get_monthly_promo():
    if MONTHLY_PROMO_TEXT:
        return MONTHLY_PROMO_TEXT
    return "🔥 เช็กราคาล่าสุด / ดูส่วนลด / เช็กโปรส่งฟรีก่อนสั่งซื้อ"


def local_score(p):
    score = 0
    score += p["rating"] * 45
    score += p["sold"] * 0.8
    score += p["category_score"] * 12
    score += p["discount_percentage"] * 3

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


def fetch_shopee_products():
    log("STEP 1: fetch shopee api")

    # match_id อาจเปลี่ยนตามหมวด/ประเทศ ถ้า endpoint นี้ใช้ไม่ได้ในบางเวลา
    # จะ fallback ด้วยการจบแบบชัดเจนใน log
    url = "https://shopee.co.th/api/v4/search/search_items"
    params = {
        "by": "sales",
        "limit": LIMIT_API,
        "newest": 0,
        "order": "desc",
        "page_type": "search"
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    r = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()

    items = data.get("items", [])
    log(f"STEP 2: raw items = {len(items)}")

    keyword_products = []
    fallback_products = []

    for wrapped in items:
        item = wrapped.get("item_basic", {})

        name = item.get("name", "")
        if not name:
            continue

        rating = safe_float(item.get("item_rating", {}).get("rating_star", 0), 0)
        sold = safe_int(item.get("historical_sold", 0), 0)

        if rating < MIN_RATING or sold < MIN_SOLD:
            continue

        itemid = item.get("itemid")
        shopid = item.get("shopid")
        image = item.get("image")

        if not itemid or not shopid or not image:
            continue

        product_link = f"https://shopee.co.th/product/{shopid}/{itemid}"
        image_url = f"https://cf.shopee.co.th/file/{image}"

        # Shopee price มักเป็นหน่วยย่อย
        price_raw = item.get("price_min") or item.get("price") or 0
        price_num = safe_float(price_raw, 0) / 100000 if price_raw else 0
        if price_num <= 0:
            continue

        original_raw = item.get("price_before_discount") or 0
        original_price_num = safe_float(original_raw, 0) / 100000 if original_raw else 0

        discount_percentage = 0
        if original_price_num > 0 and price_num > 0 and original_price_num > price_num:
            discount_percentage = round(((original_price_num - price_num) / original_price_num) * 100, 2)

        has_promo = discount_percentage > 0

        category, category_score = detect_category(name)

        product = {
            "name": name[:120],
            "product_link": product_link,
            "aff_link": make_aff_link(product_link),
            "price": f"{price_num:.2f}",
            "original_price": f"{original_price_num:.2f}" if original_price_num > 0 else "",
            "sale_price": f"{price_num:.2f}",
            "price_num": price_num,
            "rating": rating,
            "sold": sold,
            "has_promo": has_promo,
            "discount_percentage": discount_percentage,
            "category": category,
            "category_score": category_score,
            "images": [image_url][:MAX_IMAGES_PER_POST]
        }

        fallback_products.append(product)

        if allow_product(name):
            keyword_products.append(product)

    # ถ้ามีของตรงหมวดเพจ ใช้กองนี้ก่อน
    base = keyword_products if keyword_products else fallback_products
    log(f"STEP 3: valid products = {len(base)}")
    return base


def build_candidate_pool(products, posted_links):
    fresh = [p for p in products if p["product_link"] not in posted_links]
    base_pool = fresh or products

    promo_pool = [p for p in base_pool if p["has_promo"]]
    if promo_pool:
        pool = sorted(promo_pool, key=local_score, reverse=True)[:TOP_POOL]
        log(f"STEP 4: using promo pool = {len(pool)}")
        return pool

    pool = sorted(base_pool, key=local_score, reverse=True)[:TOP_POOL]
    log(f"STEP 4: no promo items, fallback pool = {len(pool)}")
    return pool


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
            "has_promo": p["has_promo"],
            "discount_percentage": p["discount_percentage"],
            "rating": p["rating"],
            "sold": p["sold"]
        })

    prompt = f"""
คุณเป็น AI ผู้ช่วยเลือกสินค้าสำหรับเพจ Facebook ชื่อ BEN Home & Electrical

เลือกสินค้า 1 ชิ้นที่เหมาะที่สุดจากรายการด้านล่าง

หลักการ:
- ต้องตรงเพจสายอุปกรณ์ไฟฟ้า ของใช้ไฟฟ้า งานช่างไฟ ของใช้ในบ้าน
- rating สูงดีกว่า
- sold สูงดีกว่า
- ถ้ามีโปรให้ความสำคัญเพิ่ม
- ถ้าไม่มีโปร ให้เลือกตัวที่ขายง่ายที่สุด
- ราคาไม่แรงมากจะดีกว่า

ตอบเป็นเลข index อย่างเดียว ห้ามมีคำอื่น

รายการ:
{json.dumps(compact, ensure_ascii=False)}
"""

    try:
        r = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
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
มีโปร: {product["has_promo"]}
ส่วนลด: {product["discount_percentage"]}%

เงื่อนไข:
- โทนขายของจริง อ่านง่าย
- มี emoji พอประมาณ
- บอกว่าสินค้าตรงหมวดกับเพจ
- ถ้ามีโปรให้ชูจุดคุ้มค่า
- ถ้าไม่มีโปรให้เน้นรีวิวดีและยอดขายดี
- ไม่เกิน 8 บรรทัดก่อนลิงก์
- ห้ามพูดเกินจริง
- บรรทัดสุดท้ายก่อนลิงก์ให้เป็น "🛒 สั่งซื้อสินค้า"
- ไม่ต้องใส่ลิงก์ในคำตอบ
- ใส่ข้อความนี้แบบเนียน ๆ: {promo}
"""

    try:
        r = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
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
    log("STEP 5: upload image")

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
        payload[f"attached_media[{i}]"] = f'{{"media_fbid":"{media_id}"}}'

    log("STEP 6: create post")
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
    log("START V35")
    validate_env()

    state = load_state()

    products = fetch_shopee_products()
    if not products:
        log("No products found")
        return

    candidate_pool = build_candidate_pool(products, set(state["posted_links"]))
    if not candidate_pool:
        log("No candidate pool")
        return

    product = ai_select_product(candidate_pool)

    log(f"STEP 4A: chosen = {product['name']}")
    log(f"STEP 4B: category = {product['category']}")
    log(f"STEP 4C: rating = {product['rating']}, sold = {product['sold']}, promo = {product['has_promo']}")

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
