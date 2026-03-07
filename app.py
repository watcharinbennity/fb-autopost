import os
import csv
import json
import random
import requests

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

AFF_ID = "15328100363"
STATE_FILE = "state.json"


def log(x):
    print(x, flush=True)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"posted": []}
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def clean_link(url):
    if not url:
        return ""
    url = url.strip()
    return url.split("?")[0]


def convert_affiliate_link(product_url):

    base = clean_link(product_url)

    return f"{base}?affiliate_id={AFF_ID}"


def read_csv():

    r = requests.get(CSV_URL, timeout=20, stream=True)

    lines = (
        line.decode("utf-8", errors="ignore")
        for line in r.iter_lines()
        if line
    )

    reader = csv.DictReader(lines)

    rows = []

    for i, row in enumerate(reader):

        rows.append(row)

        if i > 2000:
            break

    random.shuffle(rows)

    log(f"rows {len(rows)}")

    return rows


def choose_product(rows, state):

    for row in rows:

        link = clean_link(row.get("product_link"))

        if not link:
            continue

        if link in state["posted"]:
            continue

        image = row.get("image_link")

        if not image:
            continue

        return {
            "title": row.get("title"),
            "link": link,
            "image": image,
            "price": row.get("sale_price"),
            "rating": row.get("item_rating"),
            "sold": row.get("item_sold")
        }

    return None


def ai_caption(product, link):

    if not OPENAI_API_KEY:
        return None

    prompt = f"""
เขียนแคปชั่นขายสินค้าให้เพจ BEN Home & Electrical

สินค้า: {product['title']}
ราคา: {product['price']}
รีวิว: {product['rating']}
ขายแล้ว: {product['sold']}

ให้สั้น น่าเชื่อถือ มี emoji และ hashtag
"""

    try:

        r = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4.1-mini",
                "input": prompt
            }
        )

        data = r.json()

        return data["output"][0]["content"][0]["text"]

    except:
        return None


def fallback_caption(product):

    return f"""
⚡ แนะนำจาก BEN Home & Electrical

{product['title']}

⭐ รีวิว {product['rating']}
🔥 ขายแล้ว {product['sold']}
💰 ราคา {product['price']} บาท

#BENHomeElectrical #ShopeeAffiliate
"""


def upload_photo(image):

    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    r = requests.post(
        url,
        data={
            "url": image,
            "published": "false",
            "access_token": TOKEN
        }
    ).json()

    return r["id"]


def create_post(media, text):

    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    r = requests.post(
        url,
        data={
            "message": text,
            "attached_media[0]": json.dumps({"media_fbid": media}),
            "access_token": TOKEN
        }
    ).json()

    return r


def comment_link(post_id, link):

    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"

    requests.post(
        url,
        data={
            "message": f"🛒 ลิงก์สั่งซื้อ\n{link}",
            "access_token": TOKEN
        }
    )


def main():

    state = load_state()

    rows = read_csv()

    product = choose_product(rows, state)

    if not product:

        log("fallback product")

        r = rows[0]

        product = {
            "title": r.get("title"),
            "link": clean_link(r.get("product_link")),
            "image": r.get("image_link"),
            "price": r.get("sale_price"),
            "rating": r.get("item_rating"),
            "sold": r.get("item_sold")
        }

    aff_link = convert_affiliate_link(product["link"])

    caption = ai_caption(product, aff_link)

    if not caption:
        caption = fallback_caption(product)

    media = upload_photo(product["image"])

    res = create_post(media, caption)

    log(res)

    if "id" in res:

        comment_link(res["id"], aff_link)

        state["posted"].append(product["link"])

        save_state(state)

        log("POST SUCCESS")


if __name__ == "__main__":
    main()
