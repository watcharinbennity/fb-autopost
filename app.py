import os
import io
import csv
import json
import random
import requests
from datetime import datetime, timezone, timedelta

# ======================
# CONFIG
# ======================

GRAPH_VERSION="v25.0"
GRAPH_BASE=f"https://graph.facebook.com/{GRAPH_VERSION}"

PAGE_ID=os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN=os.getenv("PAGE_ACCESS_TOKEN")
SHOPEE_CSV_URL=os.getenv("SHOPEE_CSV_URL")

STATE_FILE="state.json"

STREAM_SAMPLE=25000
POST_IMAGES=3

POST_TIMES=["09:00","12:15","15:30","18:30","21:00"]

# ======================
# MARKETING TEXT
# ======================

HOOKS=[
"🔥 ของมันต้องมีติดบ้าน",
"⚡ งานช่างง่ายขึ้นด้วยไอเท็มนี้",
"🏠 ของใช้ในบ้านที่ควรมี",
"💪 เครื่องมือดี งานก็ง่าย",
"🧰 ช่างมือโปรยังใช้",
"✨ ไอเท็มยอดนิยมตอนนี้",
]

CTA=[
"👉 กดดูรายละเอียด / ราคา ล่าสุด",
"👉 เช็คราคาและโปรโมชั่นล่าสุด",
"👉 กดสั่งซื้อผ่านลิงก์นี้ได้เลย",
"👉 ดูรีวิวและราคาได้ที่ลิงก์",
]

HASHTAGS=[
"#BENHomeElectrical",
"#ของใช้ในบ้าน",
"#เครื่องมือช่าง",
"#อุปกรณ์ไฟฟ้า",
"#งานช่าง",
"#ซ่อมบ้าน",
"#ของดีบอกต่อ",
"#เครื่องมือช่างราคาดี",
]

# ======================
# TIME
# ======================

def now_bkk():
    return datetime.now(timezone(timedelta(hours=7)))

def is_post_time():
    now=now_bkk().strftime("%H:%M")
    return now in POST_TIMES

# ======================
# STATE
# ======================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {"used":[],"first":True}

    try:
        with open(STATE_FILE,"r") as f:
            return json.load(f)
    except:
        return {"used":[],"first":True}

def save_state(state):
    with open(STATE_FILE,"w") as f:
        json.dump(state,f)

# ======================
# STREAM CSV (SAFE)
# ======================

def stream_products():

    print("Streaming Shopee CSV")

    r=requests.get(
        SHOPEE_CSV_URL,
        stream=True,
        headers={"User-Agent":"Mozilla/5.0"},
        timeout=(20,60)
    )

    r.raise_for_status()

    wrapper=io.TextIOWrapper(r.raw,encoding="utf-8-sig")

    reader=csv.DictReader(wrapper)

    sample=[]

    for i,row in enumerate(reader):

        name=row.get("title") or row.get("name")
        url=row.get("product_link") or row.get("url")

        if not name or not url:
            continue

        images=[]

        for n in range(1,11):

            key=f"image_link_{n}"

            if row.get(key):
                images.append(row.get(key))

        if row.get("image_link"):
            images.append(row.get("image_link"))

        if len(images)==0:
            continue

        sample.append({
            "name":name,
            "url":url,
            "images":list(dict.fromkeys(images))
        })

        if len(sample)>=STREAM_SAMPLE:
            break

    print("Products:",len(sample))

    return sample

# ======================
# PRODUCT RANKING
# ======================

def rank_products(products):

    ranked=[]

    for p in products:

        score=random.random()

        name=p["name"].lower()

        if "sale" in name:
            score+=0.5

        if "pro" in name:
            score+=0.3

        if "tool" in name:
            score+=0.3

        if "kit" in name:
            score+=0.2

        if "set" in name:
            score+=0.2

        ranked.append((score,p))

    ranked.sort(reverse=True,key=lambda x:x[0])

    return [x[1] for x in ranked]

# ======================
# PICK PRODUCT
# ======================

def pick_product(products,state):

    ranked=rank_products(products)

    used=set(state["used"])

    fresh=[p for p in ranked if p["url"] not in used]

    pool=fresh if fresh else ranked

    product=random.choice(pool[:150])

    state["used"].append(product["url"])

    return product

# ======================
# CAPTION BUILDER
# ======================

def build_caption(product):

    hook=random.choice(HOOKS)
    cta=random.choice(CTA)

    tags=" ".join(HASHTAGS)

    return f"""
{hook}

🛒 {product['name']}

{cta}

{product['url']}

{tags}
""".strip()

# ======================
# IMAGE
# ======================

def download_image(url):

    r=requests.get(url,timeout=(20,60))

    return r.content

# ======================
# FACEBOOK GRAPH API
# ======================

def upload_photo(img):

    url=f"{GRAPH_BASE}/{PAGE_ID}/photos"

    files={"source":("img.jpg",img)}

    data={"published":"false"}

    r=requests.post(
        url,
        params={"access_token":PAGE_ACCESS_TOKEN},
        data=data,
        files=files
    )

    r.raise_for_status()

    return r.json()["id"]

def create_post(message,media_ids):

    url=f"{GRAPH_BASE}/{PAGE_ID}/feed"

    data={"message":message}

    for i,mid in enumerate(media_ids):

        data[f"attached_media[{i}]"]=json.dumps({
            "media_fbid":mid
        })

    r=requests.post(
        url,
        params={"access_token":PAGE_ACCESS_TOKEN},
        data=data
    )

    r.raise_for_status()

    return r.json()["id"]

# ======================
# POST PRODUCT
# ======================

def post_product(product):

    imgs=product["images"][:POST_IMAGES]

    caption=build_caption(product)

    media=[]

    for url in imgs:

        img=download_image(url)

        mid=upload_photo(img)

        media.append(mid)

    pid=create_post(caption,media)

    return pid

# ======================
# MAIN
# ======================

def main():

    print("Affiliate Bot V8")

    state=load_state()

    if state.get("first",True):

        print("First run post")

        products=stream_products()

        product=pick_product(products,state)

        pid=post_product(product)

        print("Post ID:",pid)

        state["first"]=False

        save_state(state)

        return

    if not is_post_time():

        print("Not post time")

        return

    products=stream_products()

    product=pick_product(products,state)

    pid=post_product(product)

    print("Post success:",pid)

    save_state(state)

if __name__=="__main__":
    main()
