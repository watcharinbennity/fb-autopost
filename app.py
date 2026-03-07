import os
import csv
import json
import random
import requests

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")
AFF_ID = os.getenv("SHOPEE_AFFILIATE_ID")

STATE_FILE="state.json"

KEYWORDS=[
"ไฟ","led","โคม","solar",
"ปลั๊ก","สวิตช์","สายไฟ",
"เครื่องมือ","ช่าง","ไขควง",
"สว่าน","diy"
]

CAPTIONS=[

"""⚡ ของมันต้องมีติดบ้าน

{name}

⭐ รีวิว {rating}
🔥 ขายแล้ว {sold}
💰 ราคา {price} บาท

🛒 {link}
""",

"""🔧 เครื่องมือช่างขายดี

{name}

⭐ {rating}
📦 {sold} คนซื้อแล้ว

💰 {price} บาท

👉 {link}
""",

"""🏠 อุปกรณ์ไฟฟ้าขายดี

{name}

⭐ รีวิว {rating}
🔥 ขายแล้ว {sold}

💰 ราคา {price}

🛒 {link}
"""
]

def load_state():

    if not os.path.exists(STATE_FILE):
        return {"posted":[]}

    with open(STATE_FILE) as f:
        return json.load(f)

def save_state(state):

    with open(STATE_FILE,"w") as f:
        json.dump(state,f)

def clean_link(url):

    if not url:
        return ""

    return url.split("?")[0]

def aff_link(url):

    return f"{clean_link(url)}?affiliate_id={AFF_ID}"

def match_category(title):

    title=title.lower()

    for k in KEYWORDS:
        if k in title:
            return True

    return False

def read_csv():

    r=requests.get(CSV_URL)

    lines=r.text.splitlines()

    reader=csv.DictReader(lines)

    rows=list(reader)

    random.shuffle(rows)

    return rows

def score(row):

    try:
        rating=float(row.get("item_rating") or 0)
    except:
        rating=0

    try:
        sold=int(float(row.get("item_sold") or 0))
    except:
        sold=0

    try:
        price=float(row.get("sale_price") or row.get("price") or 0)
    except:
        price=0

    if rating<4.5:
        return 0

    if sold<100:
        return 0

    if price<20 or price>300:
        return 0

    return rating*40 + sold*0.5

def choose_product(rows,state):

    pool=[]

    for r in rows:

        title=r.get("title") or ""

        if not match_category(title):
            continue

        link=clean_link(r.get("product_link"))
        image=r.get("image_link")

        if not link or not image:
            continue

        if link in state["posted"]:
            continue

        s=score(r)

        if s==0:
            continue

        pool.append((s,r))

    if not pool:
        return None

    pool.sort(reverse=True)

    row=random.choice(pool[:40])[1]

    return {
        "name":row.get("title"),
        "link":clean_link(row.get("product_link")),
        "image":row.get("image_link"),
        "price":row.get("sale_price") or row.get("price"),
        "rating":row.get("item_rating"),
        "sold":row.get("item_sold")
    }

def build_caption(p):

    temp=random.choice(CAPTIONS)

    return temp.format(
        name=p["name"],
        rating=p["rating"],
        sold=p["sold"],
        price=p["price"],
        link=aff_link(p["link"])
    )

def upload_photo(url):

    endpoint=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    r=requests.post(endpoint,data={
        "url":url,
        "published":"false",
        "access_token":TOKEN
    })

    return r.json()["id"]

def post_image(media,text):

    endpoint=f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    r=requests.post(endpoint,data={
        "message":text,
        "attached_media[0]":json.dumps({"media_fbid":media}),
        "access_token":TOKEN
    })

    return r.json()

def comment_link(post_id,link):

    endpoint=f"https://graph.facebook.com/v25.0/{post_id}/comments"

    requests.post(endpoint,data={
        "message":f"🛒 ลิงก์สั่งซื้อ\n{link}",
        "access_token":TOKEN
    })

def main():

    state=load_state()

    rows=read_csv()

    p=choose_product(rows,state)

    if not p:
        print("NO PRODUCT")
        return

    caption=build_caption(p)

    media=upload_photo(p["image"])

    res=post_image(media,caption)

    if "id" in res:

        comment_link(res["id"],aff_link(p["link"]))

        state["posted"].append(p["link"])

        save_state(state)

        print("POST SUCCESS")

if __name__=="__main__":
    main()
