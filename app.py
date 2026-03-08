import os
import csv
import io
import json
import random
import requests

PAGE_ID = os.environ["PAGE_ID"]
PAGE_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]
CSV_URL = os.environ["SHOPEE_CSV_URL"]
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

POST_DB = "posted.json"

# -------------------------
# KEYWORDS
# -------------------------

ALLOW_KEYWORDS = [
"led","light","lamp","lighting","solar","โซล่า","โซลาร์เซลล์",
"หลอดไฟ","โคมไฟ","ไฟ","ปลั๊ก","ปลั๊กไฟ","socket","plug",
"charger","adapter","usb","สายไฟ","extension","power strip",
"electrical","electric","อุปกรณ์ไฟฟ้า","เครื่องใช้ไฟฟ้า",
"tool","tools","hardware","เครื่องมือ","เครื่องมือช่าง",
"ไขควง","สว่าน","คีม","ประแจ",
"switch","breaker","voltage","power",
"battery","solar light","led strip",
"multimeter","tester"
]

BLOCK_KEYWORDS = [
"เสื้อ","กางเกง","รองเท้า","กระเป๋า","ลิป","ครีม","น้ำหอม",
"วิตามิน","อาหารเสริม","เครื่องสำอาง","แฟชั่น","fashion",
"dress","shirt","pants","cosmetic","perfume","makeup"
]


# -------------------------
# HISTORY
# -------------------------

def load_posted():
    if os.path.exists(POST_DB):
        with open(POST_DB,"r",encoding="utf-8") as f:
            return json.load(f)
    return []

def save_posted(data):
    with open(POST_DB,"w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)


# -------------------------
# HELPERS
# -------------------------

def parse_float(v):
    try:
        return float(str(v).replace(",",""))
    except:
        return 0

def format_price(v):
    try:
        return f"{float(v):,.0f} บาท"
    except:
        return ""


# -------------------------
# PRODUCT FILTER
# -------------------------

def is_relevant(row,name):

    text = (
        name + " " +
        (row.get("global_category1") or "") +
        (row.get("global_category2") or "") +
        (row.get("global_category3") or "")
    ).lower()

    for b in BLOCK_KEYWORDS:
        if b in text:
            return False

    for a in ALLOW_KEYWORDS:
        if a in text:
            return True

    return False


# -------------------------
# LOAD CSV
# -------------------------

def load_csv_products():

    print("STEP: load csv",flush=True)

    r = requests.get(CSV_URL,stream=True,timeout=60)
    r.raise_for_status()

    lines=[]

    for line in r.iter_lines():

        if not line:
            continue

        if isinstance(line,bytes):
            line=line.decode("utf-8","ignore")

        lines.append(line)

        # อ่าน 20000 rows
        if len(lines)>20000:
            break

    text="\n".join(lines)

    reader=csv.DictReader(io.StringIO(text))

    products=[]

    for row in reader:

        name=(row.get("title") or "").strip()

        link=(row.get("product_short link") or "").strip()

        image=(
            row.get("image_link")
            or row.get("additional_image_link")
            or ""
        ).strip()

        price=parse_float(row.get("price") or 0)
        rating=parse_float(row.get("item_rating") or 0)
        sold=parse_float(row.get("item_sold") or 0)

        if not name: continue
        if not link: continue
        if not image: continue

        if not is_relevant(row,name): continue
        if rating<4.2: continue
        if sold<10: continue
        if price<50 or price>3000: continue

        products.append({
            "name":name,
            "link":link,
            "image":image,
            "price":price,
            "rating":rating,
            "sold":sold
        })

    print("CSV PRODUCTS:",len(products),flush=True)

    return products


# -------------------------
# CAPTION
# -------------------------

def ai_caption(product):

    price=format_price(product["price"])

    fallback=f"""🔥 ของใช้ในบ้านน่าใช้

{product['name']}

💰 ราคา {price}

เหมาะกับบ้าน งานช่าง และงานไฟฟ้า
ดูรายละเอียดสินค้าได้ที่ลิงก์ด้านล่าง 👇

#BENHomeElectrical #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง
"""

    if not OPENAI_KEY:
        return fallback

    try:

        headers={
        "Authorization":f"Bearer {OPENAI_KEY}",
        "Content-Type":"application/json"
        }

        data={
        "model":"gpt-4.1-mini",
        "messages":[
        {"role":"user","content":f"""
เขียนโพสต์ Facebook สำหรับขายสินค้า

สินค้า: {product['name']}
ราคา: {price}

เงื่อนไข
- สั้น
- น่าซื้อ
- ห้ามพูดยอดขาย
- ห้ามใส่ลิงก์
- ห้ามใช้ hashtag ShopeeAffiliate
"""}
        ]
        }

        r=requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=data,
        timeout=20
        )

        r.raise_for_status()

        return r.json()["choices"][0]["message"]["content"]

    except Exception as e:

        print("OPENAI ERROR:",e,flush=True)

        return fallback


# -------------------------
# POST
# -------------------------

def post_facebook(product,caption):

    print("STEP: facebook post",flush=True)

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    payload={
    "url":product["image"],
    "caption":caption,
    "access_token":PAGE_TOKEN
    }

    r=requests.post(url,data=payload)

    data=r.json()

    print("POST RESPONSE:",data,flush=True)

    return data


# -------------------------
# COMMENT LINK
# -------------------------

def comment_link(post_id,link):

    print("STEP: comment affiliate",flush=True)

    url=f"https://graph.facebook.com/v25.0/{post_id}/comments"

    payload={
    "message":f"🛒 สั่งซื้อสินค้า\n{link}",
    "access_token":PAGE_TOKEN
    }

    r=requests.post(url,data=payload)

    print("COMMENT:",r.text,flush=True)


# -------------------------
# PICK PRODUCT
# -------------------------

def pick_product(products):

    posted=load_posted()

    candidates=[p for p in products if p["link"] not in posted]

    if not candidates:

        print("NO NEW PRODUCT",flush=True)

        return None

    # sort
    candidates.sort(
    key=lambda x:(x["rating"],x["sold"]),
    reverse=True
    )

    # top 20
    pool=candidates[:20]

    return random.choice(pool)


# -------------------------
# RUN
# -------------------------

def run():

    products=load_csv_products()

    if not products:
        print("NO PRODUCTS",flush=True)
        return

    product=pick_product(products)

    if not product:
        return

    caption=ai_caption(product)

    caption=f"""{caption}

🛒 สั่งซื้อสินค้า
{product['link']}
"""

    res=post_facebook(product,caption)

    post_id=res.get("post_id") or res.get("id")

    if not post_id:
        print("POST FAIL")
        return

    comment_link(post_id,product["link"])

    posted=load_posted()
    posted.append(product["link"])
    save_posted(posted)

    print("POST SUCCESS")


if __name__=="__main__":
    run()
