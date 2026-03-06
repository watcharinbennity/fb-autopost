import os
import csv
import json
import random
import requests
from urllib.parse import quote

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")
AFF_ID = os.getenv("SHOPEE_AFFILIATE_ID")

STATE_FILE = "state.json"

MAX_SCAN_ROWS = 5000
MAX_ROWS = 2500
HTTP_TIMEOUT = 20


KEYWORDS = [
    "led","lamp","solar","ไฟ","โคม","ปลั๊ก",
    "สายไฟ","สวิตช์","tool","ไขควง",
    "สว่าน","multimeter","adapter"
]


CAPTIONS = [

"""⚡ แนะนำจาก BEN Home & Electrical

{name}

⭐ รีวิว {rating}
🔥 ขายแล้ว {sold}
💰 ราคา {price} บาท

🛒 กดสั่งซื้อ
{link}

#BENHomeElectrical #ShopeeAffiliate""",

"""🔥 สินค้าขายดี

{name}

⭐ {rating}
📦 ขายแล้ว {sold}
💰 {price} บาท

👉 {link}

#BENHomeElectrical #ShopeeAffiliate"""
]


def log(t):
    print(t, flush=True)


def load_state():

    if not os.path.exists(STATE_FILE):
        return {"posted":[]}

    try:
        with open(STATE_FILE,"r") as f:
            data=json.load(f)
    except:
        return {"posted":[]}

    if "posted" not in data:
        data["posted"]=[]

    return data


def save_state(s):

    with open(STATE_FILE,"w") as f:
        json.dump(s,f)


def aff(link):

    return f"https://shopee.ee/an_redir?affiliate_id={AFF_ID}&origin_link={quote(link)}"


def read_feed():

    log("STEP1 read csv")

    r=requests.get(CSV_URL,timeout=HTTP_TIMEOUT,stream=True)

    r.raise_for_status()

    line_iter=(line.decode("utf-8-sig","ignore") for line in r.iter_lines() if line)

    reader=csv.DictReader(line_iter)

    rows=[]

    for i,row in enumerate(reader):

        if i>=MAX_SCAN_ROWS:
            break

        rows.append(row)

    random.shuffle(rows)

    rows=rows[:MAX_ROWS]

    log(f"rows {len(rows)}")

    return rows


def allow(name):

    n=name.lower()

    return any(k in n for k in KEYWORDS)


def build_pool(rows,state):

    pool=[]

    posted=set(state["posted"])

    for r in rows:

        title=r.get("title","")

        link=r.get("product_link","")

        img=r.get("image_link","")

        try:
            sold=int(float(r.get("item_sold",0)))
        except:
            sold=0

        try:
            rating=float(r.get("item_rating",0))
        except:
            rating=0

        price=r.get("sale_price","")

        if not title or not link or not img:
            continue

        if link in posted:
            continue

        if not allow(title):
            continue

        if rating<4.0:
            continue

        if sold<20:
            continue

        pool.append({

            "title":title,

            "link":link,

            "img":img,

            "rating":rating,

            "sold":sold,

            "price":price
        })

    log(f"valid {len(pool)}")

    return pool


def caption(p):

    link=aff(p["link"])

    c=random.choice(CAPTIONS)

    return c.format(

        name=p["title"],

        rating=p["rating"],

        sold=p["sold"],

        price=p["price"],

        link=link
    )


def upload(img):

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    r=requests.post(

        url,

        data={

            "url":img,

            "published":"false",

            "access_token":TOKEN

        }

    ).json()

    if "id" not in r:
        raise RuntimeError(r)

    return r["id"]


def post(p):

    media=upload(p["img"])

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    r=requests.post(

        url,

        data={

            "message":caption(p),

            "attached_media[0]":json.dumps({"media_fbid":media}),

            "access_token":TOKEN

        }

    ).json()

    return r


def comment(post_id,link):

    url=f"https://graph.facebook.com/v25.0/{post_id}/comments"

    r=requests.post(

        url,

        data={

            "message":f"🛒 สั่งซื้อ\n{link}",

            "access_token":TOKEN

        }

    ).json()

    return r


def main():

    state=load_state()

    rows=read_feed()

    pool=build_pool(rows,state)

    if not pool:

        log("no product")

        return

    p=random.choice(pool)

    res=post(p)

    log(res)

    if "id" in res:

        link=aff(p["link"])

        comment(res["id"],link)

        state["posted"].append(p["link"])

        save_state(state)

        log("done")


if __name__=="__main__":

    main()
