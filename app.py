import os
import csv
import json
import random
from urllib.parse import quote

import requests


PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")
AFF_ID = os.getenv("SHOPEE_AFFILIATE_ID")

STATE_FILE = "state.json"

HTTP_TIMEOUT = 20
MAX_ROWS = 5000
TOP_POOL = 15

MIN_RATING = 4.5
MIN_SOLD = 100

ALLOWED_KEYWORDS = [
    "ปลั๊ก", "ปลั๊กไฟ", "สวิตช์", "เต้ารับ", "รางปลั๊ก",
    "สายไฟ", "สายไฟฟ้า", "คอนเนคเตอร์", "เทอร์มินอล",
    "หลอดไฟ", "โคมไฟ", "led", "lamp", "light", "bulb",
    "breaker", "relay", "adapter", "ups", "solar", "inverter",
    "plug", "socket", "switch", "wire", "cable", "connector", "terminal",
    "ไขควง", "คีม", "สว่าน", "multimeter", "tester", "tool",
    "พัดลม", "หม้อแปลง", "อะแดปเตอร์", "สปอตไลท์", "ไฟเส้น",
    "ไฟโซล่า", "ไฟประดับ", "ไฟกระพริบ", "โซล่าเซลล์"
]

BLOCK_KEYWORDS = [
    "เสื้อ", "กางเกง", "รองเท้า", "กระเป๋า", "ลิป", "ครีม",
    "shirt", "pants", "shoes", "bag", "cosmetic", "toy", "food", "snack"
]


def log(msg):
    print(msg, flush=True)


def validate_env():
    missing = []
    for key, value in {
        "PAGE_ID": PAGE_ID,
        "PAGE_ACCESS_TOKEN": TOKEN,
        "SHOPEE_CSV_URL": CSV_URL,
        "SHOPEE_AFFILIATE_ID": AFF_ID,
    }.items():
        if not value:
            missing.append(key)

    if missing:
        raise ValueError("Missing env vars: " + ", ".join(missing))


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"posted_links": []}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("posted_links", [])
        return data
    except Exception:
        return {"posted_links": []}


def save_state(state):
    state["posted_links"] = state["posted_links"][-1000:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def safe_float(x):
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return 0.0


def safe_int(x):
    try:
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return 0


def pick(row, keys):
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def normalize_text(text):
    return " ".join((text or "").lower().split())


def allow_product(name):
    n = normalize_text(name)

    if any(bad in n for bad in BLOCK_KEYWORDS):
        return False

    return any(kw in n for kw in ALLOWED_KEYWORDS)


def category_score(name):
    n = normalize_text(name)
    score = 0
    for kw in ALLOWED_KEYWORDS:
        if kw in n:
            score += 1
    return score


def make_aff_link(link):
    return f"https://shopee.ee/an_redir?affiliate_id={AFF_ID}&origin_link={quote(link, safe='')}"


def has_promo(row, sale_price, original_price):
    discount = safe_float(pick(row, [
        "discount_percentage", "discount", "discount_percent"
    ]))

    if discount > 0:
        return True, discount

    sale_num = safe_float(sale_price)
    original_num = safe_float(original_price)

    if original_num > 0 and sale_num > 0 and original_num > sale_num:
        discount = round(((original_num - sale_num) / original_num) * 100, 2)
        return True, discount

    return False, 0


def load_products_from_feed():
    log("STEP 1: read feed url")

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
            log(f"STEP 1A: fields = {list(row.keys())}")

        name = pick(row, [
            "title", "product_name", "name", "item_name", "product title", "model_names"
        ])
        link = pick(row, [
            "product_link", "link", "item_link", "url"
        ])
        sale_price = pick(row, [
            "sale_price", "item_price", "model_price", "model_prices", "price"
        ])
        original_price = pick(row, [
            "price", "original_price", "item_original_price"
        ])
        rating = safe_float(pick(row, [
            "item_rating", "rating", "avg_rating", "shop_rating"
        ]))
        sold = safe_int(pick(row, [
            "item_sold", "historical_sold", "sold", "sales"
        ]))
        image = pick(row, [
            "image_link", "image", "main_image", "image_url", "additional_image_link"
        ])

        if not name or not link or not image:
            continue

        if rating < MIN_RATING:
            continue

        if sold < MIN_SOLD:
            continue

        if not allow_product(name):
            continue

        price_num = safe_float(sale_price or original_price)
        if price_num <= 0:
            continue

        promo_flag, discount_percent = has_promo(row, sale_price, original_price)

        products.append({
            "name": name[:150],
            "link": link,
            "aff": make_aff_link(link),
            "price": str(sale_price or original_price).strip(),
            "rating": rating,
            "sold": sold,
            "image": image,
            "promo": promo_flag,
            "discount": discount_percent,
            "cat_score": category_score(name)
        })

    log(f"STEP 2: valid products = {len(products)}")
    return products


def score_product(p):
    s = 0
    s += p["rating"] * 40
    s += p["sold"] * 0.6
    s += p["cat_score"] * 15

    if p["promo"]:
        s += 20

    s += p["discount"] * 2

    price_num = safe_float(p["price"])
    if price_num < 100:
        s += 20
    elif price_num < 300:
        s += 15
    elif price_num < 800:
        s += 8

    s += random.random() * 5
    return s


def choose_product(products, state):
    fresh = [p for p in products if p["link"] not in state["posted_links"]]

    if not fresh:
        fresh = products

    promo_pool = [p for p in fresh if p["promo"]]
    if promo_pool:
        ranked = sorted(promo_pool, key=score_product, reverse=True)
        log(f"STEP 3: using promo pool = {len(ranked)}")
    else:
        ranked = sorted(fresh, key=score_product, reverse=True)
        log(f"STEP 3: fallback pool = {len(ranked)}")

    pool = ranked[:TOP_POOL]
    chosen = random.choice(pool)

    log(f"STEP 4: chosen = {chosen['name']}")
    log(f"STEP 4A: rating = {chosen['rating']}, sold = {chosen['sold']}, promo = {chosen['promo']}")
    return chosen


def make_caption(p):
    promo_line = "🔥 มีโปร/ส่วนลด คุ้มก่อนสั่งซื้อ" if p["promo"] else "⭐ รีวิวดี ยอดขายสูง น่าใช้"

    caption = f"""
⚡ แนะนำจาก BEN Home & Electrical

{p['name']}

{promo_line}
⭐ รีวิว {p['rating']}
🔥 ขายแล้ว {p['sold']}
💰 ราคา {p['price']} บาท

🛒 สั่งซื้อสินค้า
{p['aff']}

#BENHomeElectrical
#ShopeeAffiliate
#อุปกรณ์ไฟฟ้า
""".strip()

    return caption


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
        raise RuntimeError(f"upload failed: {data}")
    return data["id"]


def post_product(product):
    log("STEP 5: upload image")

    media_id = upload_photo(product["image"])
    log(f"STEP 5A: uploaded image id = {media_id}")

    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    payload = {
        "message": make_caption(product),
        "attached_media[0]": json.dumps({"media_fbid": media_id}),
        "access_token": TOKEN
    }

    log("STEP 6: create post")

    data = graph_post(endpoint, payload)
    if "id" not in data:
        log(f"post failed: {data}")
        return None

    return data["id"]


def main():
    log("START V60")

    validate_env()
    state = load_state()
    products = load_products_from_feed()

    if not products:
        log("NO PRODUCT")
        return

    product = choose_product(products, state)
    post_id = post_product(product)

    if post_id:
        log(f"POSTED: {post_id}")
        state["posted_links"].append(product["link"])
        save_state(state)
    else:
        log("POST FAILED")


if __name__ == "__main__":
    main()
