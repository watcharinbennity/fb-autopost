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
MAX_ROWS = 2000
TOP_POOL = 30

MIN_RATING = 4.7
MIN_SOLD = 500

KEYWORDS = [
    "led", "light", "lamp", "solar",
    "ปลั๊ก", "ปลั๊กไฟ", "สายไฟ",
    "โคมไฟ", "ไฟ", "สปอตไลท์",
    "tool", "ไขควง", "สว่าน"
]

CAPTIONS = [
    """⚡ แนะนำจาก BEN Home & Electrical

{name}

⭐ รีวิว {rating}
🔥 ขายแล้ว {sold}
💰 ราคา {price} บาท

🛒 สั่งซื้อ
{link}

#BENHomeElectrical #ShopeeAffiliate""",

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


def valid(p):
    rating = safe_float(p.get("item_rating", 0))
    sold = safe_int(p.get("item_sold", 0))

    if rating < MIN_RATING:
        return False
    if sold < MIN_SOLD:
        return False
    if not allow(p.get("title", "")):
        return False
    return True


def score(p):
    rating = safe_float(p.get("item_rating", 0))
    sold = safe_int(p.get("item_sold", 0))
    s = rating * 40 + sold * 0.6

    name = (p.get("title", "") or "").lower()
    for k in KEYWORDS:
        if k in name:
            s += 20

    s += random.random() * 25
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
        if i >= MAX_ROWS:
            break
        if i == 0:
            log(f"STEP 1A: fields = {list(row.keys())}")
        rows.append(row)

    log(f"STEP 1B: loaded rows = {len(rows)}")
    return rows


def pick_product(products, state):
    pool = []

    for p in products:
        link = p.get("product_link")

        if link in state["posted_links"]:
            continue

        if not valid(p):
            continue

        pool.append(p)

    log(f"STEP 2: valid products = {len(pool)}")

    if not pool:
        return None

    ranked = sorted(pool, key=score, reverse=True)
    top = ranked[:TOP_POOL]
    chosen = random.choice(top)

    log(f"STEP 3: chosen = {chosen.get('title')}")
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
    log("STEP 4: upload image")

    media_id = upload(product.get("image_link"))
    log(f"STEP 4A: media id = {media_id}")

    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    payload = {
        "message": caption(product),
        "attached_media[0]": json.dumps({"media_fbid": media_id}),
        "access_token": TOKEN
    }

    log("STEP 5: create post")
    data = graph_post(endpoint, payload)
    return data


def main():
    log("START FIXED BOT")
    validate_env()

    state = load_state()
    products = read_feed()

    product = pick_product(products, state)
    if not product:
        log("NO PRODUCT")
        return

    res = post(product)
    log(f"STEP 6: post result = {res}")

    if "id" in res:
        state["posted_links"].append(product.get("product_link"))
        save_state(state)
        log("DONE")
    else:
        log("POST FAILED")


if __name__ == "__main__":
    main()
