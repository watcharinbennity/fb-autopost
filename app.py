import json
import random
import os
import requests
from datetime import datetime,timedelta,timezone

from shopee_scraper import update_products

PAGE_ID=os.getenv("PAGE_ID")
TOKEN=os.getenv("PAGE_ACCESS_TOKEN")

ASSET_DIR="assets"

PRODUCT_FILE="products.json"
POSTED_FILE="posted_products.json"
LOG_FILE="post_log.json"

TH_TZ=timezone(timedelta(hours=7))


def load_json(file):

    try:
        with open(file,"r",encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_json(file,data):

    with open(file,"w",encoding="utf-8") as f:
        json.dump(data,f,indent=2,ensure_ascii=False)


def get_mode():

    now=datetime.now(TH_TZ)

    minute=now.hour*60+now.minute

    if 9*60<=minute<10*60:
        return "viral"

    if 12*60<=minute<13*60:
        return "product"

    if 18*60+30<=minute<19*60+30:
        return "product"

    if 21*60<=minute<22*60:
        return "engage"

    return None


def pick_product():

    products=load_json(PRODUCT_FILE)

    posted=set(load_json(POSTED_FILE))

    good=[]

    for p in products:

        if p["link"] in posted:
            continue

        if p["rating"]>=4 and p["sold"]>=10:
            good.append(p)

    if not good:
        return None

    product=random.choice(good[:20])

    posted.add(product["link"])

    save_json(POSTED_FILE,list(posted))

    return product


def caption(name):

    templates=[

    f"⚡ {name}\n\nของดีแนะนำ",
    f"🔥 {name}\n\nของมันต้องมี",
    f"🛠 {name}\n\nใครใช้อยู่บ้าง"

    ]

    return random.choice(templates)


def image(category):

    if category=="solar":
        return f"{ASSET_DIR}/solar.jpg"

    if category=="plug":
        return f"{ASSET_DIR}/safe_plug.jpg"

    if category=="tools":
        return f"{ASSET_DIR}/tools.jpg"

    return f"{ASSET_DIR}/home_electrical_5.jpg"


def post(caption,image):

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    with open(image,"rb") as f:

        files={"source":f}

        data={
        "caption":caption,
        "access_token":TOKEN
        }

        r=requests.post(url,data=data,files=files)

    try:
        return r.json()["post_id"]
    except:
        print(r.text)
        return None


def comment(post_id,link):

    url=f"https://graph.facebook.com/v25.0/{post_id}/comments"

    data={
    "message":f"🛒 สั่งซื้อ\n{link}",
    "access_token":TOKEN
    }

    requests.post(url,data=data)


def run():

    print("update products")

    update_products()

    mode=get_mode()

    if mode is None:

        print("manual run → force product")

        mode="product"

    if mode=="product":

        product=pick_product()

        if not product:
            print("no product")
            return

        cap=caption(product["name"])

        img=image(product["category"])

        post_id=post(cap,img)

        if post_id:

            comment(post_id,product["link"])

        return


    if mode=="viral":

        cap="⚡ ไฟโซล่าดีไหม\n\nบ้านใครใช้อยู่บ้าง"

        post(cap,image("tools"))

        return


    if mode=="engage":

        cap="บ้านคุณใช้หลอดไฟ LED หรือยัง"

        post(cap,image("tools"))

        return


if __name__=="__main__":

    run()
