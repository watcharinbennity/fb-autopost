import json
import random
import os
import requests
from datetime import datetime, timedelta, timezone

from shopee_scraper import update_products

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
OPENAI = os.getenv("OPENAI_API_KEY")

ASSET_DIR="assets"

PRODUCT_FILE="products.json"
POSTED_FILE="posted_products.json"
LOG_FILE="post_log.json"

TH_TZ = timezone(timedelta(hours=7))


def load_json(file):

    try:
        with open(file,"r",encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_json(file,data):

    with open(file,"w",encoding="utf-8") as f:
        json.dump(data,f,indent=2,ensure_ascii=False)


def get_mode_by_time():

    now=datetime.now(TH_TZ)

    h=now.hour
    m=now.minute

    minute=h*60+m

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

        if not p.get("link"):
            continue

        if p["link"] in posted:
            continue

        rating=float(p.get("rating",0))
        sold=int(p.get("sold",0))

        if rating>=4 and sold>=10:
            good.append(p)

    if not good:
        return None

    good.sort(key=lambda x:(x["sold"],x["rating"]),reverse=True)

    product=random.choice(good[:20])

    posted.add(product["link"])

    save_json(POSTED_FILE,list(posted))

    return product


def ai_caption(name):

    if not OPENAI:

        captions=[
            f"⚡ {name}\n\nของดีที่ควรมีติดบ้าน",
            f"🔥 {name}\n\nของมันต้องมี",
            f"🛠 {name}\n\nใครใช้อยู่บ้าง"
        ]

        return random.choice(captions)

    prompt=f"""
เขียนโพสต์ Facebook ขายสินค้า

สินค้า: {name}

ให้โพสต์สั้น กระตุ้นให้คลิก
"""

    try:

        r=requests.post(

            "https://api.openai.com/v1/responses",

            headers={
                "Authorization":f"Bearer {OPENAI}",
                "Content-Type":"application/json"
            },

            json={
                "model":"gpt-4.1-mini",
                "input":prompt
            }

        )

        data=r.json()

        return data["output"][0]["content"][0]["text"]

    except:

        return f"⚡ {name}\n\nของดีแนะนำ"


def viral_caption():

    posts=[
        "⚡ ไฟโซล่าดีไหม\n\nบ้านใครใช้อยู่บ้าง",
        "🔌 ปลั๊กไฟแบบไหนปลอดภัยที่สุด",
        "🛠 เครื่องมือช่างที่ควรมีติดบ้าน"
    ]

    return random.choice(posts)


def engage_caption():

    posts=[
        "บ้านคุณใช้หลอดไฟ LED หรือยัง",
        "เครื่องมือช่างที่ใช้บ่อยคืออะไร",
        "เคยใช้ไฟโซล่าหรือยัง"
    ]

    return random.choice(posts)


def ensure_image_exists(path):

    if os.path.exists(path):
        return path

    fallback=[

        os.path.join(ASSET_DIR,"solar.jpg"),
        os.path.join(ASSET_DIR,"safe_plug.jpg"),
        os.path.join(ASSET_DIR,"tools.jpg"),
        os.path.join(ASSET_DIR,"home_electrical_5.jpg")

    ]

    for f in fallback:

        if os.path.exists(f):
            print("IMAGE FALLBACK →",f)
            return f

    raise Exception("NO IMAGE")


def get_image(category):

    if category=="solar":
        return ensure_image_exists(os.path.join(ASSET_DIR,"solar.jpg"))

    if category=="plug":
        return ensure_image_exists(os.path.join(ASSET_DIR,"safe_plug.jpg"))

    if category=="tools":
        return ensure_image_exists(os.path.join(ASSET_DIR,"tools.jpg"))

    return ensure_image_exists(os.path.join(ASSET_DIR,"home_electrical_5.jpg"))


def post(caption,image):

    image=ensure_image_exists(image)

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    with open(image,"rb") as f:

        files={"source":f}

        data={

            "caption":caption,
            "access_token":TOKEN
        }

        r=requests.post(url,data=data,files=files)

    try:

        res=r.json()

        print("POST RESPONSE:",res)

        return res.get("post_id")

    except:

        print(r.text)

        return None


def comment(post_id,link):

    url=f"https://graph.facebook.com/v25.0/{post_id}/comments"

    data={

        "message":f"🛒 สั่งซื้อ\n{link}",
        "access_token":TOKEN
    }

    try:

        r=requests.post(url,data=data)

        print("COMMENT:",r.json())

    except:

        pass


def log_post(type,name):

    logs=load_json(LOG_FILE)

    logs.append({

        "type":type,
        "name":name,
        "time":str(datetime.now(TH_TZ))
    })

    save_json(LOG_FILE,logs)


def run():

    print("Updating Shopee products")

    update_products()

    mode=get_mode_by_time()

    if mode is None:

        print("MANUAL RUN → FORCE PRODUCT")

        mode="product"

    print("MODE:",mode)


    if mode=="product":

        product=pick_product()

        if not product:

            print("NO PRODUCT")

            return

        caption=ai_caption(product["name"])

        image=get_image(product["category"])

        post_id=post(caption,image)

        if post_id:

            comment(post_id,product["link"])

        log_post("product",product["name"])

        return


    if mode=="viral":

        caption=viral_caption()

        image=get_image("tools")

        post(caption,image)

        log_post("viral","viral_post")

        return


    if mode=="engage":

        caption=engage_caption()

        image=get_image("tools")

        post(caption,image)

        log_post("engage","question")

        return


if __name__=="__main__":

    run()
