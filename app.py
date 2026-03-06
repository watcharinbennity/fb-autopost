import os
import csv
import json
import random
import requests

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")
AFF_ID = os.getenv("SHOPEE_AFFILIATE_ID")

STATE_FILE = "state.json"


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"posted_links": []}

    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def read_csv():
    r = requests.get(CSV_URL)
    r.raise_for_status()

    lines = r.text.splitlines()
    reader = csv.DictReader(lines)

    return list(reader)


def valid_product(row):

    rating = float(row.get("item_rating", 0))
    sold = int(row.get("item_sold", 0))

    if rating < 4.7:
        return False

    if sold < 500:
        return False

    return True


def make_aff(link):

    return f"https://shope.ee/an_redir?affiliate_id={AFF_ID}&origin_link={link}"


def pick_product(products, state):

    pool = []

    for p in products:

        link = p.get("product_link")

        if link in state["posted_links"]:
            continue

        if not valid_product(p):
            continue

        pool.append(p)

    if not pool:
        return None

    return random.choice(pool)


def make_caption(p):

    name = p.get("title")
    rating = p.get("item_rating")
    sold = p.get("item_sold")
    price = p.get("sale_price")
    link = make_aff(p.get("product_link"))

    caption = f"""
⚡ แนะนำจาก BEN Home & Electrical

{name}

⭐ รีวิว {rating}
🔥 ขายแล้ว {sold}
💰 ราคา {price} บาท

🛒 สั่งซื้อสินค้า
{link}

#BENHomeElectrical
#ShopeeAffiliate
#อุปกรณ์ไฟฟ้า
"""

    return caption


def post(product):

    image = product.get("image_link")
    caption = make_caption(product)

    photo_url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    r = requests.post(photo_url, data={
        "url": image,
        "published": "false",
        "access_token": TOKEN
    })

    media_id = r.json()["id"]

    post_url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    r = requests.post(post_url, data={
        "message": caption,
        "attached_media[0]": json.dumps({"media_fbid": media_id}),
        "access_token": TOKEN
    })

    return r.json()


def main():

    state = load_state()

    products = read_csv()

    product = pick_product(products, state)

    if not product:
        print("no product")
        return

    res = post(product)

    link = product.get("product_link")

    state["posted_links"].append(link)

    save_state(state)

    print("posted", res)


if __name__ == "__main__":
    main()
