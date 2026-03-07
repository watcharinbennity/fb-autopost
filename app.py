import os
import csv
import json
import random
import requests

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AFF_ID = os.getenv("SHOPEE_AFFILIATE_ID")

STATE_FILE = "state.json"
HTTP_TIMEOUT = 30

KEYWORDS = [
"ไฟ","led","โคม","solar","หลอดไฟ","ปลั๊ก","สวิตช์",
"เครื่องมือ","ช่าง","ไขควง","สว่าน","สายไฟ",
"diy","โคมไฟ","พัดลม","ปั๊ม","hardware"
]


def log(x):
    print(x, flush=True)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"posted":[]}
    with open(STATE_FILE,"r",encoding="utf8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE,"w",encoding="utf8") as f:
        json.dump(state,f,ensure_ascii=False,indent=2)


def clean_link(url):
    return (url or "").split("?")[0].strip()


def build_affiliate(url):
    base = clean_link(url)
    return f"{base}?affiliate_id={AFF_ID}"


def category_match(title):
    t = title.lower()
    for k in KEYWORDS:
        if k in t:
            return True
    return False


def read_csv():

    r = requests.get(CSV_URL,timeout=HTTP_TIMEOUT,stream=True)
    r.raise_for_status()

    lines = (
        line.decode("utf8","ignore")
        for line in r.iter_lines()
        if line
    )

    reader = csv.DictReader(lines)

    rows=[]
    for row in reader:
        rows.append(row)

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

    return rating*40 + sold*0.6


def choose_product(rows,state):

    pool=[]

    for r in rows:

        title=(r.get("title") or "").strip()

        if not category_match(title):
            continue

        link=clean_link(r.get("product_link"))
        image=(r.get("image_link") or "").strip()

        if not link or not image:
            continue

        if link in state["posted"]:
            continue

        pool.append((score(r),r))

    if not pool:
        return None

    pool.sort(key=lambda x:x[0],reverse=True)

    row=random.choice(pool[:30])[1]

    return {
        "title":row.get("title"),
        "link":clean_link(row.get("product_link")),
        "image":row.get("image_link"),
        "price":row.get("sale_price") or row.get("price"),
        "rating":row.get("item_rating"),
        "sold":row.get("item_sold")
    }


def ai_caption(product):

    if not OPENAI_API_KEY:
        return None

    try:

        r=requests.post(
        "https://api.openai.com/v1/responses",
        headers={
        "Authorization":f"Bearer {OPENAI_API_KEY}",
        "Content-Type":"application/json"
        },
        json={
        "model":"gpt-4.1-mini",
        "input":f"""
เขียนแคปชั่นขายสินค้า

สินค้า: {product['title']}
ราคา: {product['price']}
รีวิว: {product['rating']}
ขายแล้ว: {product['sold']}

ใช้ emoji เล็กน้อย
"""
        },
        timeout=HTTP_TIMEOUT
        )

        data=r.json()

        return data["output"][0]["content"][0]["text"]

    except:
        return None


def fallback(product,link):

    return f"""⚡ แนะนำจาก BEN Home & Electrical

{product['title']}

⭐ รีวิว {product['rating']}
🔥 ขายแล้ว {product['sold']}
💰 ราคา {product['price']} บาท

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

    if not PAGE_ID:
        raise ValueError("Missing PAGE_ID")

    if not TOKEN:
        raise ValueError("Missing PAGE_ACCESS_TOKEN")

    state=load_state()

    rows=read_csv()

    product=choose_product(rows,state)

    if not product:
        log("no product")
        return

    link=build_affiliate(product["link"])

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

        log("POST SUCCESS")

    else:

        log(res)


if __name__=="__main__":
    main()
