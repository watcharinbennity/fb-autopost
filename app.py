import os
import json
import random
import requests
import pandas as pd
from openai import OpenAI

PAGE_ID = os.environ["PAGE_ID"]
TOKEN = os.environ["PAGE_ACCESS_TOKEN"]
CSV_URL = os.environ["SHOPEE_CSV_URL"]
AFF_ID = os.environ["SHOPEE_AFFILIATE_ID"]

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

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


def load_products():

    df=pd.read_csv(CSV_URL)

    df=df[df["rating"]>4.5]

    df=df[df["sold"]>100]

    return df.to_dict("records")


def build_link(p):

    return f"https://shopee.co.th/product/{p['shopid']}/{p['itemid']}?affiliate_id={AFF_ID}"


def ai_caption(p,link):

    try:

        prompt=f"""
เขียนโพสต์ขายของ Facebook

สินค้า:{p['name']}
ราคา:{p['price']}
ขายแล้ว:{p['sold']}
รีวิว:{p['rating']}

ใส่ emoji
"""

        r=client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}]
        )

        text=r.choices[0].message.content

        return f"""{text}

🛒 สั่งซื้อ
{link}

#BENHomeElectrical #ShopeeAffiliate
"""

    except:
        return None


def fallback(p,link):

    return f"""
⚡ แนะนำสินค้า

{p['name']}

⭐ รีวิว {p['rating']}
🔥 ขายแล้ว {p['sold']}
💰 ราคา {p['price']} บาท

🛒 สั่งซื้อ
{link}

#ShopeeAffiliate
"""


def post(image,caption):

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    data={
    "url":image,
    "caption":caption,
    "access_token":TOKEN
    }

    r=requests.post(url,data=data)

    return r.json()


def comment(post_id,link):

    url=f"https://graph.facebook.com/v25.0/{post_id}/comments"

    data={
    "message":f"🛒 ลิงก์สั่งซื้อ\n{link}",
    "access_token":TOKEN
    }

    requests.post(url,data=data)


def pick(products,posted):

    items=[p for p in products if str(p["itemid"]) not in posted]

    if not items:
        return None

    return random.choice(items)


def main():

    state=load_state()

    products=load_products()

    p=pick(products,state["posted"])

    if not p:
        print("no product")
        return

    link=build_link(p)

    caption=ai_caption(p,link)

    if not caption:
        caption=fallback(p,link)

    res=post(p["image"],caption)

    if "post_id" not in res:
        print(res)
        return

    comment(res["post_id"],link)

    state["posted"].append(str(p["itemid"]))

    save_state(state)

    print("posted:",p["name"])


if __name__=="__main__":
    main()
