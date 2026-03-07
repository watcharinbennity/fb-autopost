import os
import csv
import json
import random
import requests

from ai_engine import choose_product, generate_caption
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


def read_csv():

    r=requests.get(CSV_URL)

    rows=list(csv.DictReader(r.text.splitlines()))

    random.shuffle(rows)

    return rows


def aff_link(url):

    url=url.split("?")[0]

    return f"{url}?affiliate_id={AFF_ID}"


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

    products=filter_products(rows,state)

    if not products:
        print("NO PRODUCT")
        return

    product=choose_product(products)

    caption=generate_caption(product)

    link=aff_link(product["link"])

    if caption:
        caption=f"{caption}\n\n🛒 {link}"
    else:
        caption=f"{product['name']}\n\n🛒 {link}"

    media=upload_photo(product["image"])

    res=post_image(media,caption)

    if "id" in res:

        comment_link(res["id"],link)

        state["posted"].append(product["link"])

        save_state(state)

        print("POST SUCCESS")


if __name__=="__main__":
    main()
