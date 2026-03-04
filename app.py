import os
import io
import csv
import json
import random
import requests
import time
from datetime import datetime, timezone, timedelta

# =============================
# CONFIG
# =============================

GRAPH_VERSION="v25.0"
GRAPH_BASE=f"https://graph.facebook.com/{GRAPH_VERSION}"

PAGE_ID=os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN=os.getenv("PAGE_ACCESS_TOKEN")
SHOPEE_CSV_URL=os.getenv("SHOPEE_CSV_URL")

STATE_FILE="state.json"

POST_IMAGES=3
STREAM_SAMPLE=12000

POST_TIMES=["12:15","18:30"]

# =============================
# MARKETING TEXT
# =============================

HOOKS=[
"🔥 ของมันต้องมีติดบ้าน",
"⚡ ไอเท็มงานช่างที่ควรมี",
"🏠 ของใช้ในบ้านที่ช่วยให้งานง่ายขึ้น",
"💪 เครื่องมือดี งานก็เสร็จไว",
"🧰 ช่างมือโปรก็ใช้ตัวนี้",
]

CTA=[
"👉 กดดูรายละเอียด / ราคา ล่าสุด",
"👉 เช็คราคาและโค้ดส่วนลด",
"👉 กดสั่งซื้อผ่านลิงก์นี้ได้ทันที",
]

HASHTAGS=[
"#BENHomeElectrical",
"#ของใช้ในบ้าน",
"#เครื่องมือช่าง",
"#อุปกรณ์ไฟฟ้า",
"#งานช่าง",
"#ซ่อมบ้าน",
"#ของดีบอกต่อ",
]

# =============================
# TIME
# =============================

def now_bkk():
    return datetime.now(timezone(timedelta(hours=7)))

def is_post_time():

    now=now_bkk().strftime("%H:%M")

    return now in POST_TIMES

# =============================
# STATE
# =============================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {"used":[],"first_run":True}

    try:
        with open(STATE_FILE,"r") as f:
            return json.load(f)
    except:
        return {"used":[],"first_run":True}

def save_state(state):

    with open(STATE_FILE,"w") as f:
        json.dump(state,f)

# =============================
# CSV STREAM (BIG FILE SAFE)
# =============================

def stream_products():

    print("Streaming Shopee CSV...")

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

    print("Loaded products:",len(sample))

    return sample

# =============================
# PRODUCT PICKER
# =============================

def pick_product(products,state):

    used=set(state["used"])

    fresh=[p for p in products if p["url"] not in used]

    pool=fresh if fresh else products

    product=random.choice(pool)

    state["used"].append(product["url"])

    return product

# =============================
# CAPTION BUILDER
# =============================

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

# =============================
# IMAGE DOWNLOAD
# =============================

def download_image(url):

    r=requests.get(url,timeout=(20,60))

    return r.content

# =============================
# FACEBOOK GRAPH API
# =============================

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

# =============================
# POST PRODUCT
# =============================

def post_product(product):

    images=product["images"][:POST_IMAGES]

    caption=build_caption(product)

    media=[]

    for img_url in images:

        img=download_image(img_url)

        mid=upload_photo(img)

        media.append(mid)

    pid=create_post(caption,media)

    return pid

# =============================
# MAIN
# =============================

def main():

    print("Bot started")

    state=load_state()

    # รันครั้งแรกโพสต์ทันที
    if state.get("first_run",True):

        print("First run post")

        products=stream_products()

        product=pick_product(products,state)

        pid=post_product(product)

        print("Post ID:",pid)

        state["first_run"]=False

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
