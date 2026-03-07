import os
import json
import random
import requests
import urllib.parse

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

AFF_ID = "15328100363"

PRODUCT_FILE = "products.json"
STATE_FILE = "state.json"
POST_FILE = "posted_products.json"


def load_json(file, default):
    try:
        with open(file, "r", encoding="utf8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(file, data):
    with open(file, "w", encoding="utf8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def affiliate_link(product):
    encoded = urllib.parse.quote(product)
    return f"https://shopee.ee/an_redir?affiliate_id={AFF_ID}&origin_link={encoded}"


def choose_product(products, posted):
    pool = [p for p in products if p["link"] not in posted]
    if not pool:
        return None

    ranked = sorted(pool, key=lambda x: float(x["sold"]), reverse=True)
    top = ranked[:30]
    return random.choice(top)


def caption(p, link):
    captions = [
f"""⚡ แนะนำจาก BEN Home & Electrical

{p['title']}

⭐ รีวิว {p['rating']}
🔥 ขายแล้ว {p['sold']}
💰 ราคา {p['price']} บาท

🛒 สั่งซื้อ
{link}

#BENHomeElectrical #ShopeeAffiliate
""",
f"""🔥 สินค้าขายดี

{p['title']}

⭐ {p['rating']}
📦 ขายแล้ว {p['sold']}
💰 {p['price']} บาท

👉 {link}

#ShopeeAffiliate
"""
    ]
    return random.choice(captions)


def upload_photo(img):
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"
    r = requests.post(url, data={
        "url": img,
        "published": "false",
        "access_token": TOKEN
    }).json()
    return r["id"]


def create_post(media, text):
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    r = requests.post(url, data={
        "message": text,
        "attached_media[0]": json.dumps({"media_fbid": media}),
        "access_token": TOKEN
    }).json()
    return r


def comment_link(post_id, link):
    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"
    requests.post(url, data={
        "message": f"🛒 ลิงก์สินค้า\n{link}",
        "access_token": TOKEN
    })


def main():
    products = load_json(PRODUCT_FILE, [])
    state = load_json(STATE_FILE, {"posted": []})
    posted_products = load_json(POST_FILE, [])

    if "posted" not in state:
        state["posted"] = []

    p = choose_product(products, state["posted"])

    if not p:
        print("no product")
        return

    aff = affiliate_link(p["link"])
    text = caption(p, aff)

    print("upload image")
    media = upload_photo(p["image"])

    print("create post")
    res = create_post(media, text)
    print(res)

    if "id" in res:
        comment_link(res["id"], aff)

        state["posted"].append(p["link"])
        posted_products.append(p)

        save_json(STATE_FILE, state)
        save_json(POST_FILE, posted_products)

        print("post success")


if __name__ == "__main__":
    main()
