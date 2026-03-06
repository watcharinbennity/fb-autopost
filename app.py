import os
import csv
import requests

from ai_engine import choose_product
from caption_ai import build_caption
from product_filter import allow_product
from category_ai import detect_category

PAGE_ID=os.getenv("PAGE_ID")
TOKEN=os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL=os.getenv("SHOPEE_CSV_URL")
AFF_ID=os.getenv("SHOPEE_AFFILIATE_ID")

def read_products():

    r=requests.get(CSV_URL)

    rows=r.text.splitlines()

    reader=csv.DictReader(rows)

    products=[]

    for row in reader:

        name=row.get("product_name") or row.get("name")
        price=row.get("price")
        link=row.get("product_link")
        rating=float(row.get("item_rating") or 0)
        sold=int(float(row.get("historical_sold") or 0))
        img=row.get("image_link")

        if not name or not link or not img:
            continue

        if not allow_product(name):
            continue

        price_num=float(price)

        products.append({

        "name":name,
        "price":price,
        "price_num":price_num,
        "link":link,
        "rating":rating,
        "sold":sold,
        "image":img,
        "category":detect_category(name),
        "aff_link":f"https://shopee.ee/an_redir?affiliate_id={AFF_ID}&origin_link={link}"

        })

    return products


def post_product(p):

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    payload={

    "url":p["image"],
    "caption":build_caption(p),
    "access_token":TOKEN

    }

    requests.post(url,data=payload)


def comment_link(post_id,p):

    url=f"https://graph.facebook.com/v25.0/{post_id}/comments"

    payload={

    "message":f"กดดูสินค้า 👇\n{p['aff_link']}",
    "access_token":TOKEN

    }

    requests.post(url,data=payload)


def main():

    products=read_products()

    p=choose_product(products)

    post_product(p)


if __name__=="__main__":
    main()
