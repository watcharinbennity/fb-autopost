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
MAX_SCAN_ROWS = 10000
MAX_ROWS = 4000
TOP_POOL = 30

STRICT_MIN_RATING = 4.7
STRICT_MIN_SOLD = 500

MID_MIN_RATING = 4.5
MID_MIN_SOLD = 100

LOOSE_MIN_RATING = 4.0
LOOSE_MIN_SOLD = 10

KEYWORDS = [
    "led", "light", "lamp", "solar",
    "ปลั๊ก", "ปลั๊กไฟ", "สายไฟ", "เต้ารับ", "สวิตช์", "รางปลั๊ก",
    "โคมไฟ", "ไฟ", "สปอตไลท์", "ไฟเส้น", "ไฟโซล่า", "ไฟประดับ",
    "tool", "ไขควง", "สว่าน", "คีม", "multimeter", "tester",
    "wire", "cable", "connector", "terminal", "adapter", "relay", "breaker"
]

CAPTIONS = [
    """⚡ แนะนำจาก BEN Home & Electrical

{name}

⭐ รีวิว {rating}
🔥 ขายแล้ว {sold}
💰 ราคา {price} บาท

🛒 สั่งซื้อ
{link}

#BENHomeElectrical #ShopeeAffiliate #อุปกรณ์ไฟฟ้า""",

    """🔥 สินค้าขายดี

{name}

⭐ {rating}
📦 ขายแล้ว {sold}
💰 {price} บาท

👉 {link}

#BENHomeElectrical #ShopeeAffiliate""",

    """🏠 ของมันต้องมีติดบ้าน

{name}

⭐ รีวิว {rating}
🔥 ยอดขาย {sold}

💰 {price} บาท

🛒 ซื้อสินค้า
{link}

#BENHomeElectrical"""
]


def log(msg):
    print(msg, flush=True)


def validate_env():
    missing = []
    for k, v in {
        "PAGE_ID": PAGE_ID,
        "PAGE_ACCESS_TOKEN": TOKEN,
        "SHOPEE_AFFILIATE_ID": AFF_ID,
        "SHOPEE_CSV_URL": CSV_URL,
    }.items():
        if not v:
            missing.append(k)

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


def allow(name):
    name = (name or "").lower()
    return any(k in name for k in KEYWORDS)


def keyword_score(name):
    name = (name or "").lower()
    score = 0
    for k in KEYWORDS:
        if k in name:
            score += 1
    return score


def valid_by_threshold(p, min_rating, min_sold):
    rating = safe_float(p.get("item_rating", 0))
    sold = safe_int(p.get("item_sold", 0))

    if rating < min_rating:
        return False
    if sold < min_sold:
        return False
    if not allow(p.get("title", "")):
        return False
    return True


def score(p):
    rating = safe_float(p.get("item_rating", 0))
    sold = safe_int(p.get("item_sold", 0))
    price = safe_float(p.get("sale_price", 0))
    name = p.get("title", "")

    s = 0
    s += rating * 40
    s += sold * 0.6
    s += keyword_score(name) * 20

    if price > 0:
        if price < 100:
            s += 20
        elif price < 300:
            s += 15
        elif price < 800:
            s += 8

    s += random.random() * 10
    return s


def aff(link):
    return f"https://shopee.ee/an_redir?affiliate_id={AFF_ID}&origin_link={quote(link, safe='')}"


def read_feed():
    log("STEP 1: read feed")

    r = requests.get(CSV_URL, timeout=HTTP_TIMEOUT, stream=True)
    r.raise_for_status()

    lines = (
        line.decode("utf-8-sig", errors="ignore")
        for line in r.iter_lines()
        if line
    )

    reader = csv.DictReader(lines)

    rows = []
    for i, row in enumerate(reader):
        if i >= MAX_SCAN_ROWS:
            break
        if i == 0:
            log(f"STEP 1A: fields = {list(row.keys())}")
        rows.append(row)

    random.shuffle(rows)
    rows = rows[:MAX_ROWS]

    log(f"STEP 1B: loaded rows = {len(rows)}")
    return rows


def build_pool(rows, state):
    posted = set(state["posted_links"])

    fresh_rows = []
    for r in rows:
        link = pick(r, ["product_link", "link", "item_link", "url"])
        if not link:
            continue
        if link in posted:
            continue
        fresh_rows.append(r)

    if not fresh_rows:
        fresh_rows = rows

    strict_pool = []
    mid_pool = []
    loose_pool = []

    for row in fresh_rows:
        title = pick(row, ["title", "product_name", "name", "item_name", "product title", "model_names"])
        product_link = pick(row, ["product_link", "link", "item_link", "url"])
        sale_price = pick(row, ["sale_price", "item_price", "model_price", "model_prices", "price"])
        image_link = pick(row, ["image_link", "image", "main_image", "image_url", "additional_image_link"])

        if not title or not product_link or not image_link:
            continue

        product = {
            "title": title,
            "product_link": product_link,
            "sale_price": sale_price,
            "item_rating": pick(row, ["item_rating", "rating", "avg_rating", "shop_rating"]),
            "item_sold": pick(row, ["item_sold", "historical_sold", "sold", "sales"]),
            "image_link": image_link,
        }

        if valid_by_threshold(product, STRICT_MIN_RATING, STRICT_MIN_SOLD):
            strict_pool.append(product)

        if valid_by_threshold(product, MID_MIN_RATING, MID_MIN_SOLD):
            mid_pool.append(product)

        if valid_by_threshold(product, LOOSE_MIN_RATING, LOOSE_MIN_SOLD):
            loose_pool.append(product)

    log(f"STEP 2A: strict pool = {len(strict_pool)}")
    log(f"STEP 2B: mid pool = {len(mid_pool)}")
    log(f"STEP 2C: loose pool = {len(loose_pool)}")

    if strict_pool:
        log("STEP 3: using strict pool")
        return strict_pool

    if mid_pool:
        log("STEP 3: using mid pool")
        return mid_pool

    if loose_pool:
        log("STEP 3: using loose pool")
        return loose_pool

    return []


def pick_product(pool):
    if not pool:
        return None

    ranked = sorted(pool, key=score, reverse=True)
    top = ranked[:TOP_POOL]
    chosen = random.choice(top)

    log(f"STEP 4: chosen = {chosen.get('title')}")
    log(
        f"STEP 4A: rating = {chosen.get('item_rating')}, "
        f"sold = {chosen.get('item_sold')}, "
        f"price = {chosen.get('sale_price')}"
    )
    return chosen


def caption(p):
    style = random.choice(CAPTIONS)
    return style.format(
        name=p.get("title"),
        rating=p.get("item_rating"),
        sold=p.get("item_sold"),
        price=p.get("sale_price"),
        link=aff(p.get("product_link"))
    )


def graph_post(endpoint, payload):
    r = requests.post(endpoint, data=payload, timeout=HTTP_TIMEOUT)
    return r.json()


def upload(url):
    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"
    data = graph_post(endpoint, {
        "url": url,
        "published": "false",
        "access_token": TOKEN
    })
    if "id" not in data:
        raise RuntimeError(data)
    return data["id"]


def post(product):
    log("STEP 5: upload image")

    media_id = upload(product.get("image_link"))
    log(f"STEP 5A: media id = {media_id}")

    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    payload = {
        "message": caption(product),
        "attached_media[0]": json.dumps({"media_fbid": media_id}),
        "access_token": TOKEN
    }

    log("STEP 6: create post")
    data = graph_post(endpoint, payload)
    return data


def main():
    log("START MIX10000 BOT")
    validate_env()

    state = load_state()
    rows = read_feed()
    pool = build_pool(rows, state)

    if not pool:
        log("NO PRODUCT")
        return

    product = pick_product(pool)
    if not product:
        log("NO CHOSEN PRODUCT")
        return

    res = post(product)
    log(f"STEP 7: post result = {res}")

    if "id" in res:
        state["posted_links"].append(product.get("product_link"))
        save_state(state)
        log("DONE")
    else:
        log("POST FAILED")


if __name__ == "__main__":
    main()
