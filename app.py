import os
import csv
import json
import random
import requests
from urllib.parse import quote

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")
AFF_ID = os.getenv("SHOPEE_AFFILIATE_ID")

STATE_FILE = "state.json"

MIN_RATING = 4.5
MIN_SOLD = 100

HTTP_TIMEOUT = 20


def log(msg):
    print(msg, flush=True)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"posted_links": []}

    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def safe_float(x):
    try:
        return float(str(x).replace(",", ""))
    except:
        return 0


def safe_int(x):
    try:
        return int(float(str(x).replace(",", "")))
    except:
        return 0


def pick(row, keys):
    for k in keys:
        if k in row and row[k]:
            return row[k]
    return ""


def make_aff_link(link):
    return f"https://shopee.ee/an_redir?affiliate_id={AFF_ID}&origin_link={quote(link)}"


# -------------------------
# LOAD CSV
# -------------------------

def load_products():

    log("STEP 1: load csv")

    r = requests.get(CSV_URL, timeout=HTTP_TIMEOUT, stream=True)
    r.raise_for_status()

    lines = (
        line.decode("utf-8-sig", errors="ignore")
        for line in r.iter_lines()
        if line
    )

    reader = csv.DictReader(lines)

    products = []

    for row in reader:

        name = pick(row, ["title", "name"])
        link = pick(row, ["product_link"])
        price = pick(row, ["sale_price", "price"])
        rating = safe_float(pick(row, ["item_rating"]))
        sold = safe_int(pick(row, ["item_sold"]))

        image = pick(row, ["image_link"])

        if not name or not link or not image:
            continue

        if rating < MIN_RATING:
            continue

        if sold < MIN_SOLD:
            continue

        product = {
            "name": name,
            "link": link,
            "aff": make_aff_link(link),
            "price": price,
            "rating": rating,
            "sold": sold,
            "image": image
        }

        products.append(product)

    log(f"STEP 2: valid products = {len(products)}")

    return products


# -------------------------
# AI SELECT (fallback)
# -------------------------

def choose_product(products, state):

    pool = [p for p in products if p["link"] not in state["posted_links"]]

    if not pool:
        pool = products

    pool = sorted(pool, key=lambda x: x["sold"], reverse=True)

    return random.choice(pool[:10])


# -------------------------
# CAPTION
# -------------------------

def make_caption(p):

    caption = f"""
⚡ ของดีสายไฟฟ้า

{p['name']}

⭐ รีวิว {p['rating']}
🔥 ขายแล้ว {p['sold']}

💰 ราคา {p['price']} บาท

🛒 สั่งซื้อสินค้า
{p['aff']}

#BENHomeElectrical
#ShopeeAffiliate
"""

    return caption


# -------------------------
# FACEBOOK
# -------------------------

def upload_photo(url):

    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    payload = {
        "url": url,
        "published": "false",
        "access_token": TOKEN
    }

    r = requests.post(endpoint, data=payload)
    data = r.json()

    return data["id"]


def post(product):

    log("STEP 3: upload image")

    media_id = upload_photo(product["image"])

    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    caption = make_caption(product)

    payload = {
        "message": caption,
        "attached_media[0]": json.dumps({"media_fbid": media_id}),
        "access_token": TOKEN
    }

    log("STEP 4: create post")

    r = requests.post(endpoint, data=payload)

    data = r.json()

    if "id" not in data:
        log(data)
        return None

    return data["id"]


# -------------------------
# MAIN
# -------------------------

def main():

    log("START V40")

    state = load_state()

    products = load_products()

    if not products:
        log("NO PRODUCT")
        return

    product = choose_product(products, state)

    log(f"CHOSEN: {product['name']}")

    post_id = post(product)

    if post_id:

        log(f"POSTED: {post_id}")

        state["posted_links"].append(product["link"])

        save_state(state)


if __name__ == "__main__":
    main()
