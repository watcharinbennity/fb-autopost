import os
import json
import random
import requests
from datetime import datetime
from openai import OpenAI

PAGE_ID = os.environ["PAGE_ID"]
PAGE_ACCESS_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]
AFFILIATE_ID = os.environ["SHOPEE_AFFILIATE_ID"]

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

STATE_FILE = "state.json"


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {"posted": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def load_products():
    with open("products.json") as f:
        return json.load(f)


def build_affiliate_link(product):
    product_id = product["product_id"]
    shop_id = product["shop_id"]

    return f"https://shopee.co.th/product/{shop_id}/{product_id}?affiliate_id={AFFILIATE_ID}"


def ai_caption(product, link):
    try:

        prompt = f"""
เขียนแคปชั่นขายของ Facebook ภาษาไทย

สินค้า: {product['title']}
ราคา: {product['price']} บาท
ขายแล้ว: {product['sold']}
รีวิว: {product['rating']}

ใส่ emoji และ hashtag
"""

        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )

        text = r.choices[0].message.content

        return f"""{text}

🛒 สั่งซื้อ
{link}

#BENHomeElectrical #ShopeeAffiliate
"""

    except:
        return None


def fallback_caption(product, link):

    return f"""
⚡ แนะนำจาก BEN Home & Electrical

{product['title']}

⭐ รีวิว {product['rating']}
🔥 ขายแล้ว {product['sold']}
💰 ราคา {product['price']} บาท

🛒 สั่งซื้อ
{link}

#BENHomeElectrical #ShopeeAffiliate
"""


def post_photo(image_url, caption):

    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    data = {
        "url": image_url,
        "caption": caption,
        "access_token": PAGE_ACCESS_TOKEN,
    }

    r = requests.post(url, data=data)

    return r.json()


def comment_link(post_id, link):

    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"

    msg = f"""
🛒 ลิงก์สั่งซื้อ
{link}
"""

    data = {
        "message": msg,
        "access_token": PAGE_ACCESS_TOKEN,
    }

    requests.post(url, data=data)


def pick_product(products, posted):

    items = [p for p in products if p["product_id"] not in posted]

    if not items:
        return None

    return random.choice(items)


def main():

    state = load_state()
    products = load_products()

    product = pick_product(products, state["posted"])

    if not product:
        print("no product")
        return

    aff_link = build_affiliate_link(product)

    caption = ai_caption(product, aff_link)

    if not caption:
        caption = fallback_caption(product, aff_link)

    res = post_photo(product["image"], caption)

    if "post_id" not in res:
        print(res)
        return

    post_id = res["post_id"]

    comment_link(post_id, aff_link)

    state["posted"].append(product["product_id"])

    save_state(state)

    print("POSTED:", product["title"])


if __name__ == "__main__":
    main()
