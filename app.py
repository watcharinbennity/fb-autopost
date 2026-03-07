import os
import csv
import json
import random
import requests

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")
AFF_ID = os.getenv("SHOPEE_AFFILIATE_ID")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

STATE_FILE="state.json"
TIMEOUT=30

KEYWORDS=[
"ไฟ","led","โคม","solar",
"ปลั๊ก","สวิตช์","สายไฟ",
"เครื่องมือ","ช่าง","ไขควง",
"สว่าน","diy","hardware"
]

def load_state():

    if not os.path.exists(STATE_FILE):
        return {"posted":[]}

    with open(STATE_FILE,"r") as f:
        return json.load(f)

def save_state(s):

    with open(STATE_FILE,"w") as f:
        json.dump(s,f)

def clean_link(url):

    if not url:
        return ""

    return url.split("?")[0]

def aff_link(url):

    return f"{clean_link(url)}?affiliate_id={AFF_ID}"

def category_ok(title):

    t=title.lower()

    for k in KEYWORDS:
        if k in t:
            return True

    return False

def read_csv():

    r=requests.get(CSV_URL,timeout=TIMEOUT,stream=True)
    r.raise_for_status()

    lines=(l.decode("utf8","ignore") for l in r.iter_lines() if l)

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

    return rating*50 + sold*0.5

def choose(rows,state):

    pool=[]

    for r in rows:

        title=(r.get("title") or "")

        if not category_ok(title):
            continue

        link=clean_link(r.get("product_link"))

        if not link:
            continue

        if link in state["posted"]:
            continue

        s=score(r)

        if s==0:
            continue

        pool.append((s,r))

    if not pool:
        return None

    pool.sort(key=lambda x:x[0],reverse=True)

    row=random.choice(pool[:40])[1]

    return {
        "title":row.get("title"),
        "link":clean_link(row.get("product_link")),
        "image":row.get("image_link"),
        "price":row.get("sale_price") or row.get("price"),
        "rating":row.get("item_rating"),
        "sold":row.get("item_sold")
    }

def ai_caption(p):

    if not OPENAI_KEY:
        return None

    prompt=f"""
เขียนโพสต์ขายสินค้า

สินค้า: {p['title']}
ราคา: {p['price']} บาท
รีวิว: {p['rating']}
ขายแล้ว: {p['sold']}

ทำให้ดูน่าซื้อ
ใช้ emoji
ไม่เกิน 6 บรรทัด
"""

    try:

        r=requests.post(
        "https://api.openai.com/v1/responses",
        headers={
        "Authorization":f"Bearer {OPENAI_KEY}",
        "Content-Type":"application/json"
        },
        json={
        "model":"gpt-4.1-mini",
        "input":prompt
        },
        timeout=TIMEOUT
        )

        data=r.json()

        return data["output"][0]["content"][0]["text"]

    except:
        return None

def fallback(p,link):

    return f"""
⚡ แนะนำจาก BEN Home & Electrical

{p['title']}

⭐ รีวิว {p['rating']}
🔥 ขายแล้ว {p['sold']}
💰 ราคา {p['price']} บาท

🛒 สั่งซื้อ
{link}

#BENHomeElectrical #ShopeeAffiliate
"""

def ensure_link(text,link):

    if link in text:
        return text

    return f"{text}\n\n🛒 สั่งซื้อ\n{link}"

def upload_photo(image):

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    r=requests.post(url,data={
        "url":image,
        "published":"false",
        "access_token":TOKEN
    })

    data=r.json()

    if "id" not in data:
        raise RuntimeError(data)

    return data["id"]

def create_post(media,text):

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    r=requests.post(url,data={
        "message":text,
        "attached_media[0]":json.dumps({"media_fbid":media}),
        "access_token":TOKEN
    })

    return r.json()

def comment(post_id,link):

    url=f"https://graph.facebook.com/v25.0/{post_id}/comments"

    requests.post(url,data={
        "message":f"🛒 ลิงก์สั่งซื้อ\n{link}",
        "access_token":TOKEN
    })

def main():

    state=load_state()

    rows=read_csv()

    product=choose(rows,state)

    if not product:
        print("NO PRODUCT")
        return

    link=aff_link(product["link"])

    caption=ai_caption(product)

    if not caption:
        caption=fallback(product,link)

    caption=ensure_link(caption,link)

    media=upload_photo(product["image"])

    res=create_post(media,caption)

    if "id" in res:

        comment(res["id"],link)

        state["posted"].append(product["link"])

        save_state(state)

        print("POST SUCCESS")

if __name__=="__main__":
    main()
