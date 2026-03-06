import os
import csv
import json
import random
import requests
from datetime import datetime

PAGE_ID=os.getenv("PAGE_ID")
TOKEN=os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL=os.getenv("SHOPEE_CSV_URL")
AFF_ID=os.getenv("SHOPEE_AFFILIATE_ID")

STATE_FILE="state.json"
MAX_ROWS=3000


CAPTIONS=[

"""🔥 ของมันต้องมีติดบ้าน

{name}

💰 ราคา {price} บาท
⭐ {rating}/5
📦 {sold} คนซื้อแล้ว

👇 ดูสินค้า
{link}

#BENHomeElectrical #ShopeeAffiliate""",

"""⚡ สินค้าขายดีใน Shopee

{name}

💰 {price} บาท
⭐ รีวิว {rating}/5
📦 ขายแล้ว {sold}

{link}

#ของใช้ในบ้าน #เครื่องมือช่าง"""
]


def log(x):
    print(datetime.utcnow(),x,flush=True)


def load_state():

    if not os.path.exists(STATE_FILE):

        return {"posted":[]}

    with open(STATE_FILE) as f:

        return json.load(f)


def save_state(state):

    with open(STATE_FILE,"w") as f:

        json.dump(state,f)


def read_products():

    r=requests.get(CSV_URL,timeout=60)

    rows=r.text.splitlines()

    reader=csv.DictReader(rows)

    products=[]

    for i,row in enumerate(reader):

        if i>MAX_ROWS:
            break

        name=row.get("product_name") or row.get("name")
        price=row.get("price")
        link=row.get("product_link")
        rating=row.get("item_rating") or "0"
        sold=row.get("historical_sold") or "0"

        img1=row.get("image_link")
        img2=row.get("image_link_2")
        img3=row.get("image_link_3")

        if not name or not link or not img1:
            continue

        products.append({

            "name":name,
            "price":price,
            "link":link,
            "rating":float(rating),
            "sold":int(float(sold)),
            "images":[img1,img2,img3]

        })

    return products


def score(p):

    s=0
    s+=p["sold"]/20
    s+=p["rating"]*10
    s+=random.random()*3

    return s


def choose_product(products,state):

    products.sort(key=score,reverse=True)

    for p in products[:80]:

        if p["link"] not in state["posted"]:

            return p

    return random.choice(products)


def aff_link(link):

    return f"https://shopee.ee/an_redir?affiliate_id={AFF_ID}&origin_link={link}"


def caption(p):

    temp=random.choice(CAPTIONS)

    return temp.format(

        name=p["name"],
        price=p["price"],
        rating=p["rating"],
        sold=p["sold"],
        link=aff_link(p["link"])

    )


def upload_photo(url):

    endpoint=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    payload={

        "url":url,
        "published":"false",
        "access_token":TOKEN

    }

    r=requests.post(endpoint,data=payload)

    return r.json()["id"]


def post_images(p):

    media=[]

    for img in p["images"]:

        if not img:
            continue

        try:

            mid=upload_photo(img)
            media.append(mid)

        except:
            pass

    endpoint=f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    payload={

        "message":caption(p),
        "access_token":TOKEN

    }

    for i,m in enumerate(media):

        payload[f"attached_media[{i}]"]=f'{{"media_fbid":"{m}"}}'

    r=requests.post(endpoint,data=payload)

    log(r.text)


def main():

    state=load_state()

    products=read_products()

    p=choose_product(products,state)

    post_images(p)

    state["posted"].append(p["link"])

    save_state(state)


if __name__=="__main__":

    main()
