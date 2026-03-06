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

MIN_RATING = 4.7
MIN_SOLD = 500

KEYWORDS = [
"led","light","lamp","solar",
"ปลั๊ก","ปลั๊กไฟ","สายไฟ",
"โคมไฟ","ไฟ","สปอตไลท์",
"tool","ไขควง","สว่าน"
]

CAPTION_STYLE = [
"""
⚡ แนะนำจาก BEN Home & Electrical

{title}

⭐ รีวิว {rating}
🔥 ขายแล้ว {sold}
💰 ราคา {price} บาท

🛒 สั่งซื้อสินค้า
{link}

#BENHomeElectrical
#ShopeeAffiliate
""",

"""
🔥 สินค้าขายดีจาก BEN Home & Electrical

{title}

⭐ คะแนนรีวิว {rating}
📦 ยอดขาย {sold}
💰 ราคา {price} บาท

ซื้อเลย
{link}

#ShopeeAffiliate
#BENHomeElectrical
""",

"""
⚡ ของมันต้องมี!

{title}

⭐ รีวิว {rating}
🔥 ขายไปแล้ว {sold}
💰 ราคา {price}

ดูสินค้า
{link}

#BENHomeElectrical
"""
]


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"posted_links":[]}

    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE,"w") as f:
        json.dump(state,f)


def read_feed():

    r = requests.get(CSV_URL)
    r.raise_for_status()

    lines = r.text.splitlines()

    reader = csv.DictReader(lines)

    return list(reader)


def allow_product(name):

    name = name.lower()

    for k in KEYWORDS:
        if k in name:
            return True

    return False


def valid(p):

    rating=float(p.get("item_rating",0))
    sold=int(p.get("item_sold",0))

    if rating < MIN_RATING:
        return False

    if sold < MIN_SOLD:
        return False

    if not allow_product(p.get("title","")):
        return False

    return True


def score(p):

    rating=float(p.get("item_rating",0))
    sold=int(p.get("item_sold",0))

    score = rating*40 + sold*0.6

    name=p.get("title","").lower()

    for k in KEYWORDS:
        if k in name:
            score+=20

    score += random.random()*10

    return score


def pick(products,state):

    pool=[]

    for p in products:

        link=p.get("product_link")

        if link in state["posted_links"]:
            continue

        if not valid(p):
            continue

        pool.append(p)

    if not pool:
        return None

    ranked=sorted(pool,key=score,reverse=True)

    top=ranked[:30]

    return random.choice(top)


def aff(link):

    return f"https://shope.ee/an_redir?affiliate_id={AFF_ID}&origin_link={link}"


def caption(p):

    style=random.choice(CAPTION_STYLE)

    return style.format(
        title=p.get("title"),
        rating=p.get("item_rating"),
        sold=p.get("item_sold"),
        price=p.get("sale_price"),
        link=aff(p.get("product_link"))
    )


def upload(img):

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    r=requests.post(url,data={
        "url":img,
        "published":"false",
        "access_token":TOKEN
    })

    return r.json()["id"]


def post(product):

    media=upload(product.get("image_link"))

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    r=requests.post(url,data={
        "message":caption(product),
        "attached_media[0]":json.dumps({"media_fbid":media}),
        "access_token":TOKEN
    })

    return r.json()


def main():

    state=load_state()

    products=read_feed()

    p=pick(products,state)

    if not p:
        print("no product")
        return

    res=post(p)

    state["posted_links"].append(p.get("product_link"))

    save_state(state)

    print(res)


if __name__=="__main__":
    main()
