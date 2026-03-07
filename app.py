import json
import random
import os
import requests
from datetime import datetime

PAGE_ID=os.getenv("PAGE_ID")
TOKEN=os.getenv("PAGE_ACCESS_TOKEN")
OPENAI=os.getenv("OPENAI_API_KEY")

PRODUCT_FILE="products.json"
POSTED_FILE="posted_products.json"
LOG_FILE="post_log.json"

CAPTION_FILE="captions_2000.txt"
VIRAL_FILE="viral_posts_300.json"
REELS_FILE="reels_ideas_100.json"


def load_json(file):

    try:
        with open(file,encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_json(file,data):

    with open(file,"w",encoding="utf-8") as f:
        json.dump(data,f,indent=2,ensure_ascii=False)


def load_captions():

    try:
        with open(CAPTION_FILE,encoding="utf-8") as f:
            return f.read().splitlines()
    except:
        return ["⚡ {name} ของดีสำหรับบ้าน"]


def log_post(type,name):

    data=load_json(LOG_FILE)

    data.append({
        "type":type,
        "name":name,
        "time":str(datetime.now())
    })

    save_json(LOG_FILE,data)


def pick_product():

    products=load_json(PRODUCT_FILE)
    posted=load_json(POSTED_FILE)

    good=[
        p for p in products
        if p["link"] not in posted
        and p.get("rating",4)>=4
        and p.get("sold",0)>=10
    ]

    if not good:
        return None

    product=random.choice(good)

    posted.append(product["link"])

    save_json(POSTED_FILE,posted)

    return product


def ai_caption(name):

    if not OPENAI:

        captions=load_captions()

        template=random.choice(captions)

        return template.replace("{name}",name)

    prompt=f"""
เขียนโพสต์ Facebook ขายสินค้า

สินค้า: {name}

โพสต์สั้น น่าสนใจ กระตุ้นให้คลิก
"""

    r=requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization":f"Bearer {OPENAI}",
            "Content-Type":"application/json"
        },
        json={
            "model":"gpt-4.1-mini",
            "input":prompt
        }
    )

    try:
        return r.json()["output"][0]["content"][0]["text"]
    except:

        captions=load_captions()

        template=random.choice(captions)

        return template.replace("{name}",name)


def viral_caption():

    posts=load_json(VIRAL_FILE)

    post=random.choice(posts)

    return post["caption"]


def engage_caption():

    questions=[
        "บ้านคุณใช้ปลั๊กไฟกี่ตัว ?",
        "เคยใช้ไฟโซล่าหรือยัง ?",
        "เครื่องมือช่างที่ใช้บ่อยคืออะไร ?",
        "บ้านคุณใช้หลอดไฟ LED หรือยัง ?"
    ]

    return random.choice(questions)


def reels_idea():

    reels=load_json(REELS_FILE)

    return random.choice(reels)


def get_image(category):

    if category=="solar":
        return "assets/solar.jpg"

    if category=="plug":
        return "assets/safe_plug.jpg"

    if category=="tools":
        return "assets/tools.jpg"

    if category=="led":
        return "assets/led_save_power.jpg"

    return "assets/home_electrical_5.jpg"


def post(caption,image):

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    files={"source":open(image,"rb")}

    data={
        "caption":caption,
        "access_token":TOKEN
    }

    r=requests.post(url,data=data,files=files)

    try:
        return r.json()["post_id"]
    except:
        return None


def comment(post_id,link):

    url=f"https://graph.facebook.com/v25.0/{post_id}/comments"

    data={
        "message":f"🛒 สั่งซื้อ\n{link}",
        "access_token":TOKEN
    }

    requests.post(url,data=data)


def run():

    mode=random.choice(["product","viral","engage","reels"])


    if mode=="product":

        product=pick_product()

        if product:

            caption=ai_caption(product["name"])

            image=get_image(product["category"])

            post_id=post(caption,image)

            if post_id:
                comment(post_id,product["link"])

            log_post("product",product["name"])

            return


    if mode=="viral":

        caption=viral_caption()

        post(caption,"assets/home_electrical_5.jpg")

        log_post("viral","content")


    if mode=="engage":

        caption=engage_caption()

        post(caption,"assets/home_electrical_5.jpg")

        log_post("engagement","question")


    if mode=="reels":

        idea=reels_idea()

        print("REELS IDEA:",idea)

        log_post("reels","idea")


if __name__=="__main__":

    run()
