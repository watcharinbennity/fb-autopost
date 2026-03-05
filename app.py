import os
import io
import csv
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests


# =========================
# GRAPH
# =========================

GRAPH_VERSION="v25.0"
GRAPH_BASE=f"https://graph.facebook.com/{GRAPH_VERSION}"

PAGE_ID=os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN=os.getenv("PAGE_ACCESS_TOKEN")
SHOPEE_CSV_URL=os.getenv("SHOPEE_CSV_URL")
AFFILIATE_ID=os.getenv("AFFILIATE_ID","15328100363")

STATE_FILE="state.json"

TZ=timezone(timedelta(hours=7))


# =========================
# FILTER
# =========================

PRICE_MIN=79
PRICE_MAX=1999

MIN_RATING=4.5
MIN_DISCOUNT=10
MIN_SOLD=50

TOP_POOL=200
STREAM_MAX_ROWS=300000

POST_IMAGES_COUNT=3


# =========================
# POST TIME
# =========================

POST_SLOTS=[
"09:00",
"12:15",
"15:30",
"18:30",
"21:00"
]


# =========================
# UTILS
# =========================

def now():

    return datetime.now(TZ)


def parse_slot_today(slot):

    h,m=slot.split(":")

    n=now()

    return n.replace(hour=int(h),minute=int(m),second=0,microsecond=0)


def load_state():

    if not os.path.exists(STATE_FILE):

        return{
            "used":[],
            "posted_slots":{},
            "first_run":True
        }

    with open(STATE_FILE) as f:

        return json.load(f)


def save_state(state):

    with open(STATE_FILE,"w") as f:

        json.dump(state,f)


# =========================
# AFFILIATE
# =========================

def affiliate_link(url):

    if "smtt=" in url:

        return url

    if "?" in url:

        return f"{url}&smtt=0.{AFFILIATE_ID}"

    return f"{url}?smtt=0.{AFFILIATE_ID}"


# =========================
# PRODUCT
# =========================

@dataclass
class Product:

    name:str
    url:str
    images:List[str]
    video:Optional[str]
    price:Optional[float]
    sale:Optional[float]
    discount:Optional[float]
    rating:Optional[float]
    sold:Optional[int]


def fnum(x):

    try:

        return float(str(x).replace(",",""))

    except:

        return None


def fint(x):

    try:

        return int(float(x))

    except:

        return None


# =========================
# MEDIA
# =========================

def extract_images(row):

    imgs=[]

    for i in range(1,10):

        v=row.get(f"image_link_{i}")

        if v:

            imgs.append(v)

    if row.get("image_link"):

        imgs.append(row["image_link"])

    return list(dict.fromkeys(imgs))


def extract_video(row):

    for k in["video_url","video_link","video"]:

        if row.get(k):

            return row[k]

    return None


# =========================
# NORMALIZE
# =========================

def normalize(row):

    return Product(

        row.get("name") or row.get("title"),

        row.get("url") or row.get("product_link"),

        extract_images(row),

        extract_video(row),

        fnum(row.get("price")),

        fnum(row.get("sale_price")),

        fnum(row.get("discount_percentage")),

        fnum(row.get("rating")),

        fint(row.get("sold"))

    )


# =========================
# FILTER
# =========================

def pass_filter(p):

    if not p.name or not p.url:

        return False

    if not p.images and not p.video:

        return False

    price=p.sale or p.price

    if price is None:

        return False

    if not PRICE_MIN<=price<=PRICE_MAX:

        return False

    if p.rating and p.rating<MIN_RATING:

        return False

    if p.sold and p.sold<MIN_SOLD:

        return False

    if p.discount and p.discount<MIN_DISCOUNT:

        return False

    return True


# =========================
# SCORE
# =========================

def score(p):

    r=p.rating or 4
    d=p.discount or 0
    s=p.sold or 0

    r_score=(r-4)/1
    d_score=d/70
    s_score=(s**0.5)/70

    base=(0.46*r_score)+(0.34*d_score)+(0.2*s_score)

    if s>5000:

        base*=1.2

    if d>40:

        base*=1.15

    if p.video:

        base*=1.1

    base*=random.uniform(0.96,1.04)

    return base


# =========================
# STREAM CSV
# =========================

def stream_products():

    r=requests.get(SHOPEE_CSV_URL,stream=True)

    reader=csv.DictReader(io.TextIOWrapper(r.raw,encoding="utf8"))

    top=[]

    rows=0

    for row in reader:

        rows+=1

        if rows>STREAM_MAX_ROWS:

            break

        p=normalize(row)

        if not pass_filter(p):

            continue

        sc=score(p)

        if len(top)<TOP_POOL:

            top.append((sc,p))

        else:

            worst=min(range(len(top)),key=lambda i:top[i][0])

            if sc>top[worst][0]:

                top[worst]=(sc,p)

    return top


# =========================
# CAPTION
# =========================

HOOKS=[
"🔥 ของมันต้องมีติดบ้าน",
"⚡ ตัวฮิตรีวิวดี",
"🎯 ของใช้ที่ควรมี",
]

CTA=[
"กดดูโปรล่าสุด 👇",
"เช็คราคาในลิงก์ 👇",
]

HASHTAGS=[
"#BENHomeElectrical",
"#ShopeeAffiliate",
"#ของใช้ในบ้าน"
]


def caption(p):

    hook=random.choice(HOOKS)

    cta=random.choice(CTA)

    price=p.sale or p.price

    link=affiliate_link(p.url)

    return f"""
{hook}

🛒 {p.name}

💸 ราคา {price}
⭐ {p.rating}/5
📦 ขายแล้ว {p.sold}

👉 {link}

{cta}

{" ".join(HASHTAGS)}
"""


# =========================
# GRAPH POST
# =========================

def graph_post(path,data=None,files=None):

    url=f"{GRAPH_BASE}{path}"

    r=requests.post(

        url,

        params={"access_token":PAGE_ACCESS_TOKEN},

        data=data,

        files=files,

        headers={"User-Agent":"Mozilla/5.0"}
    )

    js=r.json()

    if "error" in js:

        raise Exception(js)

    return js


# =========================
# IMAGE POST
# =========================

def upload_image(img):

    b=requests.get(img).content

    files={"source":("img.jpg",b)}

    js=graph_post(f"/{PAGE_ID}/photos",{"published":"false"},files)

    return js["id"]


def post_images(p,cap):

    media=[]

    for img in p.images[:POST_IMAGES_COUNT]:

        mid=upload_image(img)

        media.append(mid)

        time.sleep(1)

    data={"message":cap}

    for i,m in enumerate(media):

        data[f"attached_media[{i}]"]=json.dumps({"media_fbid":m})

    js=graph_post(f"/{PAGE_ID}/feed",data)

    return js["id"]


# =========================
# VIDEO POST
# =========================

def post_video(p,cap):

    data={

        "description":cap,

        "file_url":p.video,

        "published":"true"
    }

    js=graph_post(f"/{PAGE_ID}/videos",data)

    return js["id"]


# =========================
# POST ENGINE
# =========================

def run_post(state):

    top=stream_products()

    used=set(state.get("used",[]))

    fresh=[x for x in top if x[1].url not in used]

    pool=fresh if fresh else top

    sc,p=random.choice(pool)

    cap=caption(p)

    try:

        if p.video:

            vid=post_video(p,cap)

            print("video posted",vid)

        else:

            pid=post_images(p,cap)

            print("image post",pid)

    except:

        pid=post_images(p,cap)

    state.setdefault("used",[]).append(p.url)


# =========================
# CHECK SLOT
# =========================

def due_slot(state):

    today=now().strftime("%Y-%m-%d")

    posted=state.get("posted_slots",{}).get(today,[])

    for slot in POST_SLOTS:

        slot_time=parse_slot_today(slot)

        if now()>=slot_time and slot not in posted:

            return slot

    return None


# =========================
# MAIN
# =========================

def main():

    print("=== FB AUTOPOST V25 ===")

    state=load_state()

    if state.get("first_run"):

        print("First run -> post now")

        run_post(state)

        state["first_run"]=False

        save_state(state)

        return


    slot=due_slot(state)

    if not slot:

        print("No slot due")

        return


    print("Posting for slot",slot)

    run_post(state)

    today=now().strftime("%Y-%m-%d")

    state.setdefault("posted_slots",{}).setdefault(today,[]).append(slot)

    save_state(state)


if __name__=="__main__":

    main()
