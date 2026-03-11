import os
import csv
import json
import random
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

PAGE_ID = os.environ["PAGE_ID"]
PAGE_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]
CSV_URL = os.environ["SHOPEE_CSV_URL"]
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

POSTED_FILE = "posted_products.json"
THAI_TIME = ZoneInfo("Asia/Bangkok")


CATEGORY_KEYWORDS = [
    "ไฟ","led","โคม","solar","โซล่า",
    "ปลั๊ก","ปลั๊กไฟ","ปลั๊กพ่วง","สายไฟ","เบรกเกอร์",
    "charger","adapter","power","battery",
    "สว่าน","ไขควง","คีม","ประแจ","tool","tools",
    "electrical","socket","switch","lamp","light"
]


VIRAL_TOPICS = [
    "ไฟโซล่าดีไหม ใช้ในบ้านคุ้มไหม",
    "ปลั๊กไฟแบบไหนปลอดภัยสำหรับบ้าน",
    "5 เครื่องมือช่างที่ควรมีติดบ้าน",
    "หลอดไฟ LED ประหยัดไฟจริงไหม",
    "อุปกรณ์ไฟฟ้าที่ควรมีติดบ้าน"
]


ENGAGE_TOPICS = [
    "บ้านคุณใช้ปลั๊กไฟกี่จุด",
    "เครื่องมือช่างชิ้นแรกที่ควรมีคืออะไร",
    "ตอนนี้ในบ้านใช้ LED หมดหรือยัง",
    "เคยใช้ไฟโซล่ารอบบ้านไหม",
    "ของใช้ไฟฟ้าที่ขาดไม่ได้คืออะไร"
]


def load_json(path, default):
    try:
        with open(path,"r",encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


def save_json(path,data):
    with open(path,"w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)


def get_mode():

    now = datetime.now(THAI_TIME)

    h = now.hour
    m = now.minute

    hm = h*60 + m

    if 9*60 <= hm < 10*60:
        return "viral"

    if 12*60 <= hm < 13*60:
        return "product"

    if 15*60 <= hm < 16*60:
        return "engage"

    if 18*60+30 <= hm < 19*60+30:
        return "product"

    if 21*60 <= hm < 22*60:
        return "product"

    return "product"


def parse_float(v):
    try:
        return float(str(v).replace(",",""))
    except:
        return 0


def parse_int(v):
    try:
        return int(float(str(v).replace(",","")))
    except:
        return 0


def is_match(name,row):

    text = (
        name.lower()
        + str(row.get("global_category1","")).lower()
        + str(row.get("global_category2","")).lower()
        + str(row.get("global_category3","")).lower()
    )

    for k in CATEGORY_KEYWORDS:
        if k in text:
            return True

    return False


def load_csv_products():

    print("STEP: load csv")

    r = requests.get(CSV_URL,stream=True,timeout=60)
    r.raise_for_status()

    reader = csv.DictReader(
        (line.decode("utf-8","ignore") for line in r.iter_lines() if line)
    )

    products=[]
    scanned=0

    for row in reader:

        scanned+=1

        if scanned>20000:
            break

        name=(row.get("title") or "").strip()

        link=(
            row.get("product_short link")
            or row.get("product_link")
            or ""
        ).strip()

        image=(
            row.get("image_link")
            or row.get("additional_image_link")
            or ""
        ).strip()

        rating=parse_float(row.get("item_rating"))
        sold=parse_int(row.get("item_sold"))
        stock=parse_int(row.get("stock"))

        if not name or not link or not image:
            continue

        if stock<=0:
            continue

        if rating<4:
            continue

        if sold<10:
            continue

        if not is_match(name,row):
            continue

        products.append({
            "name":name,
            "link":link,
            "image":image,
            "rating":rating,
            "sold":sold
        })

        if len(products)>=300:
            break

    print("CSV SCANNED:",scanned)
    print("CSV PRODUCTS:",len(products))

    return products


def pick_product(products):

    posted=set(load_json(POSTED_FILE,[]))

    candidates=[p for p in products if p["link"] not in posted]

    if not candidates:
        return None

    candidates.sort(
        key=lambda x:(x["rating"],x["sold"]),
        reverse=True
    )

    return random.choice(candidates[:40])


def ai_text(prompt,fallback):

    if not OPENAI_KEY:
        return fallback

    try:

        r=requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization":f"Bearer {OPENAI_KEY}",
                "Content-Type":"application/json"
            },
            json={
                "model":"gpt-4.1-mini",
                "messages":[{"role":"user","content":prompt}]
            },
            timeout=30
        )

        r.raise_for_status()

        return r.json()["choices"][0]["message"]["content"]

    except Exception as e:

        print("OPENAI ERROR",e)

        return fallback


def build_product_caption(product):

    fallback=f"""
🔥 {product['name']}

ของน่าใช้สำหรับบ้านและงานไฟฟ้า
เช็กราคาล่าสุดที่ลิงก์ด้านล่าง 👇
""".strip()

    prompt=f"""
เขียนโพสต์ Facebook ภาษาไทย
สินค้า: {product['name']}

เงื่อนไข
- ห้ามใส่ราคา
- ห้ามพูดยอดขาย
- สั้น
- น่าซื้อ
- แนวเพจเครื่องใช้ไฟฟ้า
"""

    text=ai_text(prompt,fallback)

    return f"""{text}

🛒 สั่งซื้อสินค้า
{product['link']}"""


def build_viral():

    topic=random.choice(VIRAL_TOPICS)

    return f"""
⚡ {topic}

ใครเคยใช้บ้าง มาแชร์กัน 👇
"""


def build_engage():

    topic=random.choice(ENGAGE_TOPICS)

    return f"""
{topic}

คอมเมนต์กันหน่อย 👇
"""


def post_photo(image,caption):

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    r=requests.post(
        url,
        data={
            "url":image,
            "caption":caption,
            "access_token":PAGE_TOKEN
        }
    )

    print("POST:",r.text)

    return r.json()


def comment_link(post_id,link):

    requests.post(
        f"https://graph.facebook.com/v25.0/{post_id}/comments",
        data={
            "message":f"🛒 สั่งซื้อสินค้า\n{link}",
            "access_token":PAGE_TOKEN
        }
    )


def run_product():

    products=load_csv_products()

    if not products:
        return

    product=pick_product(products)

    if not product:
        return

    caption=build_product_caption(product)

    res=post_photo(product["image"],caption)

    post_id=res.get("post_id") or res.get("id")

    if not post_id:
        return

    comment_link(post_id,product["link"])

    posted=load_json(POSTED_FILE,[])
    posted.append(product["link"])
    save_json(POSTED_FILE,posted)


def run():

    mode=get_mode()

    print("MODE:",mode)

    if mode=="viral":
        post_photo("",build_viral())
        return

    if mode=="engage":
        post_photo("",build_engage())
        return

    run_product()


if __name__=="__main__":
    run()
