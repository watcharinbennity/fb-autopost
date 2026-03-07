import os
import json
import csv
import io
import random
import requests
from datetime import datetime, timezone, timedelta

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")

ASSET_DIR = "assets"

POSTED_FILE = "posted_products.json"

TH = timezone(timedelta(hours=7))


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def load_csv_products():

    print("STEP: load csv", flush=True)

    r = requests.get(CSV_URL, timeout=30)
    r.raise_for_status()

    text = r.text

    reader = csv.DictReader(io.StringIO(text))

    products = []

    for row in reader:

        name = row.get("name") or row.get("title") or ""

        link = row.get("link") or row.get("product_link") or ""

        rating = float(row.get("rating") or 0)

        sold = int(float(row.get("sold") or 0))

        if not name or not link:
            continue

        if rating >= 4 and sold >= 10:

            products.append({
                "name": name,
                "link": link,
                "rating": rating,
                "sold": sold
            })

    print("CSV PRODUCTS:", len(products), flush=True)

    return products


def pick_product():

    products = load_csv_products()

    posted = set(load_json(POSTED_FILE, []))

    candidates = [p for p in products if p["link"] not in posted]

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x["sold"], x["rating"]), reverse=True)

    product = random.choice(candidates[:20])

    posted.add(product["link"])

    save_json(POSTED_FILE, list(posted))

    return product


def post_facebook(caption, image):

    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    with open(image, "rb") as f:

        r = requests.post(
            url,
            files={"source": f},
            data={
                "caption": caption,
                "access_token": TOKEN
            }
        )

    print(r.text)

    data = r.json()

    return data.get("post_id")


def comment(post_id, link):

    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"

    requests.post(url, data={
        "message": f"🛒 สั่งซื้อ\n{link}",
        "access_token": TOKEN
    })


def caption(name):

    captions = [
        f"⚡ {name}\n\nของดีที่ควรมีติดบ้าน",
        f"🔥 {name}\n\nกำลังฮิตเลยตัวนี้",
        f"🛠 {name}\n\nใครใช้อยู่บ้าง",
        f"💡 {name}\n\nของมันต้องมี",
    ]

    return random.choice(captions)


def run():

    product = pick_product()

    if not product:

        print("NO PRODUCT")

        return

    cap = caption(product["name"])

    image = f"{ASSET_DIR}/tools.jpg"

    post_id = post_facebook(cap, image)

    if post_id:

        comment(post_id, product["link"])


if __name__ == "__main__":

    run()
