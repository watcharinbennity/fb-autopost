import os
import csv
import random
import requests
from datetime import datetime
from moviepy.editor import ImageClip, concatenate_videoclips

PAGE_ID=os.getenv("PAGE_ID")
TOKEN=os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL=os.getenv("SHOPEE_CSV_URL")
AFF_ID=os.getenv("SHOPEE_AFFILIATE_ID")

MAX_ROWS=2000
STATE_FILE="state.json"


CAPTIONS=[
"""🔥 ของมันต้องมีติดบ้าน
🛒 {name}

💰 ราคา {price} บาท
⭐ {rating} / 5
📦 ขายแล้ว {sold}

👉 ดูสินค้า
{link}

#BENHomeElectrical #ShopeeAffiliate
""",

"""⚡ สินค้าขายดีใน Shopee

{name}

💰 {price} บาท
⭐ รีวิว {rating}/5
📦 {sold} คนซื้อแล้ว

{link}

#ของใช้ในบ้าน #เครื่องมือช่าง
""",

"""🏠 BEN Home & Electrical

{name}

💰 ราคา {price} บาท

⭐ {rating} /5
📦 ขายแล้ว {sold}

👉 สั่งซื้อ
{link}
"""
]


def log(x):
    print(datetime.utcnow(),x,flush=True)


def load_state():

    if not os.path.exists(STATE_FILE):

        return {"posted":[]}

    import json

    with open(STATE_FILE) as f:

        return json.load(f)


def save_state(state):

    import json

    with open(STATE_FILE,"w") as f:

        json.dump(state,f)


def read_products():

    r=requests.get(CSV_URL,timeout=60)

    lines=r.text.splitlines()

    reader=csv.DictReader(lines)

    products=[]

    for i,row in enumerate(reader):

        if i>MAX_ROWS:
            break

        name=row.get("product_name") or row.get("name")

        price=row.get("price")

        link=row.get("product_link")

        rating=row.get("item_rating")

        sold=row.get("historical_sold")

        img1=row.get("image_link")

        img2=row.get("image_link_2")

        img3=row.get("image_link_3")

        if not name or not link or not img1:
            continue

        products.append({
        "name":name,
        "price":price,
        "link":link,
        "rating":float(rating or 0),
        "sold":int(float(sold or 0)),
        "images":[img1,img2,img3]
        })

    return products


def score_product(p):

    score=0

    score+=p["sold"]/20
    score+=p["rating"]*10
    score+=random.random()*5

    return score


def choose_product(products,state):

    products.sort(key=score_product,reverse=True)

    for p in products[:50]:

        if p["link"] not in state["posted"]:

            return p

    return random.choice(products)


def build_affiliate(link):

    return f"https://shopee.ee/an_redir?affiliate_id={AFF_ID}&origin_link={link}"


def make_caption(p):

    template=random.choice(CAPTIONS)

    return template.format(
    name=p["name"],
    price=p["price"],
    rating=p["rating"],
    sold=p["sold"],
    link=build_affiliate(p["link"])
    )


def upload_photo(url):

    endpoint=f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    payload={
    "url":url,
    "published":"false",
    "access_token":TOKEN
    }

    r=requests.post(endpoint,data=payload)

    return r.json()["id"]


def post_images(p):

    media=[]

    for img in p["images"]:

        if not img:
            continue

        try:

            mid=upload_photo(img)

            media.append(mid)

        except:

            pass

    endpoint=f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    payload={
    "message":make_caption(p),
    "access_token":TOKEN
    }

    for i,m in enumerate(media):

        payload[f"attached_media[{i}]"]=f'{{"media_fbid":"{m}"}}'

    r=requests.post(endpoint,data=payload)

    log(r.text)


def download(url,file):

    r=requests.get(url)

    open(file,"wb").write(r.content)


def make_reel(images):

    clips=[]

    for img in images:

        clip=ImageClip(img).set_duration(2)

        clips.append(clip)

    video=concatenate_videoclips(clips)

    video.write_videofile("reel.mp4",fps=24)

    return "reel.mp4"


def post_reel(p):

    imgfile="img1.jpg"

    download(p["images"][0],imgfile)

    video=make_reel([imgfile])

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/videos"

    files={"file":open(video,"rb")}

    data={
    "description":make_caption(p),
    "access_token":TOKEN
    }

    r=requests.post(url,files=files,data=data)

    log(r.text)


def main():

    state=load_state()

    products=read_products()

    p=choose_product(products,state)

    if random.random()>0.5:

        post_images(p)

    else:

        post_reel(p)

    state["posted"].append(p["link"])

    save_state(state)


if __name__=="__main__":

    main()
