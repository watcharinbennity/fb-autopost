import os
import csv
import json
import random
import requests

from ai_engine import generate_caption
from viral_engine import viral_post,engagement_post
from product_filter import filter_products

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

    r=requests.get(CSV_URL)

    rows=list(csv.DictReader(r.text.splitlines()))

    random.shuffle(rows)

    return rows


def upload_photo(url):

    endpoint=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    r=requests.post(endpoint,data={
        "url":url,
        "published":"false",
        "access_token":TOKEN
    })

    return r.json()["id"]


def create_post(media,text):

    endpoint=f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    r=requests.post(endpoint,data={
        "message":text,
        "attached_media[0]":json.dumps({"media_fbid":media}),
        "access_token":TOKEN
    })

    return r.json()


def comment(post_id,link):

    endpoint=f"https://graph.facebook.com/v25.0/{post_id}/comments"

    requests.post(endpoint,data={
        "message":f"🛒 ลิงก์สั่งซื้อ\n{link}",
        "access_token":TOKEN
    })


def fallback_product(rows):

    for r in rows:

        if r.get("product_link") and r.get("image_link"):

            return {
                "name":r.get("title"),
                "link":r.get("product_link"),
                "image":r.get("image_link"),
                "price":r.get("price"),
                "rating":0,
                "sold":0
            }


def main():

    state=load_state()

    rows=read_csv()

    mode=random.randint(1,5)

    if mode==1:

        text=viral_post()

        media=upload_photo("https://i.imgur.com/7yUVEJb.png")

        create_post(media,text)

        return

    if mode==2:

        text=engagement_post()

        media=upload_photo("https://i.imgur.com/7yUVEJb.png")

        create_post(media,text)

        return

    products=filter_products(rows,state)

    if not products:

        p=fallback_product(rows)

    else:

        p=products[0]

    link=aff_link(p["link"])

    caption=generate_caption(p)

    if not caption:

        caption=p["name"]

    caption=f"{caption}\n\n🛒 {link}"

    media=upload_photo(p["image"])

    res=create_post(media,caption)

    if "id" in res:

        comment(res["id"],link)

        state["posted"].append(p["link"])

        save_state(state)


if __name__=="__main__":
    main()
