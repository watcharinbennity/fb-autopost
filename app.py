import os
import csv
import json
import random
import requests

from ai_engine import product_caption,viral_text
from product_filter import score_product
from viral_engine import viral_post

PAGE_ID=os.getenv("PAGE_ID")
TOKEN=os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL=os.getenv("SHOPEE_CSV_URL")
AFF_ID=os.getenv("SHOPEE_AFFILIATE_ID")

STATE_FILE="state.json"

def load_state():

    try:
        with open(STATE_FILE) as f:
            return json.load(f)

    except:
        return {"posted":[]}


def save_state(state):

    with open(STATE_FILE,"w") as f:
        json.dump(state,f)


def aff_link(link):

    base=link.split("?")[0]

    return f"{base}?affiliate_id={AFF_ID}"


def read_csv():

    r=requests.get(CSV_URL,timeout=20)

    rows=list(csv.DictReader(r.text.splitlines()))

    random.shuffle(rows)

    return rows[:500]


def choose_product(rows,state):

    posted=set(state["posted"])

    best=None
    best_score=0

    for r in rows:

        name=r.get("title")

        link=r.get("product_link")

        image=r.get("image_link")

        if not name or not link or not image:
            continue

        if link in posted:
            continue

        rating=float(r.get("item_rating") or 0)

        sold=int(float(r.get("item_sold") or 0))

        price=r.get("price")

        score=score_product(name,rating,sold)

        if score>best_score:

            best_score=score

            best={
            "name":name,
            "link":link,
            "image":image,
            "price":price,
            "rating":rating,
            "sold":sold
            }

    return best


def upload_photo(url):

    endpoint=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    r=requests.post(
    endpoint,
    data={
    "url":url,
    "published":"false",
    "access_token":TOKEN
    })

    return r.json()["id"]


def post_image(media,text):

    endpoint=f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    r=requests.post(
    endpoint,
    data={
    "message":text,
    "attached_media[0]":json.dumps({"media_fbid":media}),
    "access_token":TOKEN
    })

    return r.json()


def comment_link(post_id,link):

    endpoint=f"https://graph.facebook.com/v25.0/{post_id}/comments"

    requests.post(
    endpoint,
    data={
    "message":f"🛒 สั่งซื้อ\n{link}",
    "access_token":TOKEN
    })


def main():

    state=load_state()

    mode=random.randint(1,3)

    if mode==1:

        topic,image=viral_post()

        caption=viral_text(topic)

        media=upload_photo(image)

        post_image(media,caption)

        return

    if mode==2:

        text="""
💬 คุณใช้เครื่องมือช่างอะไรบ่อยที่สุด ?

คอมเมนต์หน่อย
"""

        media=upload_photo("https://i.imgur.com/9XqvF2C.jpg")

        post_image(media,text)

        return

    rows=read_csv()

    product=choose_product(rows,state)

    if not product:
        return

    caption=product_caption(product)

    link=aff_link(product["link"])

    text=f"""{caption}

🛒 สั่งซื้อ
{link}
"""

    media=upload_photo(product["image"])

    res=post_image(media,text)

    if "id" in res:

        comment_link(res["id"],link)

    state["posted"].append(product["link"])

    save_state(state)


if __name__=="__main__":

    main()
