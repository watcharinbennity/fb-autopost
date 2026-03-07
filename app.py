import json
import random
import os
import requests
from datetime import datetime, timedelta, timezone

from shopee_scraper import update_products

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

PRODUCT_FILE = "products.json"
POSTED_FILE = "posted_products.json"
LOG_FILE = "post_log.json"

ASSET_DIR = "assets"

TH_TZ = timezone(timedelta(hours=7))


# ---------------- JSON ----------------

def load_json(file):
    try:
        with open(file,"r",encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_json(file,data):
    with open(file,"w",encoding="utf-8") as f:
        json.dump(data,f,indent=2,ensure_ascii=False)


# ---------------- LOG ----------------

def log_post(ptype,name):

    logs = load_json(LOG_FILE)

    if not isinstance(logs,list):
        logs=[]

    logs.append({
        "type":ptype,
        "name":name,
        "time":str(datetime.now(TH_TZ))
    })

    save_json(LOG_FILE,logs)


def analyze_posts():

    logs=load_json(LOG_FILE)

    stats={}

    for l in logs:

        if not isinstance(l,dict):
            continue

        t=l.get("type","unknown")

        stats[t]=stats.get(t,0)+1

    return stats


# ---------------- SCHEDULE ----------------

def get_mode():

    now=datetime.now(TH_TZ)

    m=now.hour*60+now.minute

    if 9*60 <= m < 10*60:
        return "viral"

    if 12*60 <= m < 13*60:
        return "product"

    if 18*60+30 <= m < 19*60+30:
        return "product"

    if 21*60 <= m < 22*60:
        return "engage"

    return None


# ---------------- IMAGE ----------------

def image(path):

    full=os.path.join(ASSET_DIR,path)

    if os.path.exists(full):
        return full

    fallback=[
        "solar.jpg",
        "safe_plug.jpg",
        "tools.jpg",
        "led_save_power.jpg",
        "home_electrical_5.jpg"
    ]

    for f in fallback:

        p=os.path.join(ASSET_DIR,f)

        if os.path.exists(p):
            return p

    raise Exception("NO IMAGE")


def image_by_category(cat):

    if cat=="solar":
        return image("solar.jpg")

    if cat=="plug":
        return image("safe_plug.jpg")

    if cat=="tools":
        return image("tools.jpg")

    if cat=="led":
        return image("led_save_power.jpg")

    return image("home_electrical_5.jpg")


# ---------------- CAPTION ----------------

def product_caption(name):

    captions=[

        f"⚡ {name}\n\nของดีที่ควรมีติดบ้าน",

        f"🔥 {name}\n\nกำลังฮิตตอนนี้",

        f"🛠 {name}\n\nแนะนำเลยรุ่นนี้",

        f"💡 {name}\n\nตัวนี้ขายดีมาก",

        f"⚡ {name}\n\nใครใช้อยู่บ้าง"

    ]

    return random.choice(captions)


def viral_caption():

    posts=[

        "⚡ ไฟโซล่าดีไหม\n\nบ้านใครใช้อยู่บ้าง",

        "🔌 ปลั๊กไฟแบบไหนปลอดภัยที่สุด",

        "🛠 เครื่องมือช่างที่ควรมีติดบ้าน",

        "💡 หลอดไฟ LED ประหยัดไฟจริงไหม",

        "🏠 5 อุปกรณ์ไฟฟ้าที่ควรมีติดบ้าน"

    ]

    return random.choice(posts)


def engage_caption():

    posts=[

        "บ้านคุณใช้หลอดไฟ LED หรือยัง",

        "เครื่องมือช่างที่ใช้บ่อยคืออะไร",

        "เคยใช้ไฟโซล่าหรือยัง",

        "บ้านคุณใช้ปลั๊กไฟกี่ตัว",

        "ของใช้ไฟฟ้าชิ้นไหนสำคัญสุด"

    ]

    return random.choice(posts)


# ---------------- PRODUCT ----------------

def clean_posted(raw):

    result=[]

    if not isinstance(raw,list):
        return result

    for i in raw:

        if isinstance(i,str):
            result.append(i)

        if isinstance(i,dict):
            link=i.get("link")
            if link:
                result.append(link)

    return list(dict.fromkeys(result))


def pick_product():

    products=load_json(PRODUCT_FILE)

    posted=set(clean_posted(load_json(POSTED_FILE)))

    good=[]

    for p in products:

        link=p.get("link")

        if not link:
            continue

        if link in posted:
            continue

        rating=float(p.get("rating",0))
        sold=int(p.get("sold",0))

        if rating>=4 and sold>=10:
            good.append(p)

    if not good:
        return None

    good.sort(key=lambda x:(int(x["sold"]),float(x["rating"])),reverse=True)

    product=random.choice(good[:20] if len(good)>=20 else good)

    posted.add(product["link"])

    save_json(POSTED_FILE,list(posted))

    return product


# ---------------- FACEBOOK ----------------

def post(caption,img):

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    with open(img,"rb") as f:

        files={"source":f}

        data={
            "caption":caption,
            "access_token":TOKEN
        }

        r=requests.post(url,data=data,files=files)

    res=r.json()

    print("POST RESPONSE:",res,flush=True)

    return res.get("post_id")


def comment(post_id,link):

    url=f"https://graph.facebook.com/v25.0/{post_id}/comments"

    data={
        "message":f"🛒 สั่งซื้อ\n{link}",
        "access_token":TOKEN
    }

    r=requests.post(url,data=data)

    print("COMMENT:",r.json(),flush=True)


# ---------------- MAIN ----------------

def run():

    print("Updating Shopee products",flush=True)

    update_products()

    mode=get_mode()

    if mode is None:

        print("MANUAL RUN -> FORCE PRODUCT",flush=True)

        mode="product"

    print("MODE:",mode,flush=True)


    if mode=="product":

        p=pick_product()

        if not p:
            print("NO PRODUCT")
            return

        caption=product_caption(p["name"])

        img=image_by_category(p.get("category",""))

        post_id=post(caption,img)

        if post_id:
            comment(post_id,p["link"])

        log_post("product",p["name"])


    if mode=="viral":

        caption=viral_caption()

        img=image("tools.jpg")

        post(caption,img)

        log_post("viral","viral")


    if mode=="engage":

        caption=engage_caption()

        img=image("tools.jpg")

        post(caption,img)

        log_post("engage","engage")


    print("POST STATS:",analyze_posts(),flush=True)


if __name__=="__main__":

    run()
