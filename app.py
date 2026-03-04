import os
import io
import csv
import json
import random
import time
import requests

GRAPH_VERSION = "v25.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

POST_IMAGES_COUNT = 3
STATE_FILE = "state.json"

HASHTAGS = [
    "#BENHomeElectrical",
    "#ของใช้ในบ้าน",
    "#อุปกรณ์ไฟฟ้า",
    "#เครื่องมือช่าง",
    "#งานช่าง",
    "#ซ่อมบ้าน",
    "#ของดีบอกต่อ"
]

HOOKS = [
    "ของมันต้องมีติดบ้าน 🏠",
    "งานช่างง่ายขึ้นทันที 🔧",
    "ของดีราคาคุ้ม 💪",
    "อุปกรณ์ที่ควรมีติดบ้าน 🔥"
]

CTA = [
    "👉 กดดูรายละเอียดที่ลิงก์",
    "👉 สนใจดูสินค้าได้ที่ลิงก์",
    "👉 เช็คราคาและรายละเอียด"
]


def env(name):
    v = os.getenv(name)
    if not v:
        raise SystemExit(f"Missing env {name}")
    return v


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"posted": []}
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def fetch_csv(url):
    r = requests.get(url)
    r.raise_for_status()
    return r.content.decode("utf-8-sig")


def normalize(row):

    name = row.get("title") or row.get("name") or ""
    url = row.get("product_link") or row.get("url") or ""

    images = []

    for k in row.keys():
        if k.startswith("image_link"):
            if row[k]:
                images.append(row[k])

    images = list(dict.fromkeys(images))

    key = row.get("itemid") or url or name

    return {
        "name": name.strip(),
        "url": url.strip(),
        "images": images,
        "key": key
    }


def parse_products(text):

    reader = csv.DictReader(io.StringIO(text))
    products = []

    for r in reader:

        p = normalize(r)

        if p["name"] and p["url"] and p["images"]:
            products.append(p)

    if not products:
        raise SystemExit("CSV has no usable rows")

    return products


def build_caption(p):

    lines = []

    lines.append(random.choice(HOOKS))
    lines.append("")
    lines.append(p["name"])
    lines.append("")
    lines.append(random.choice(CTA))
    lines.append(p["url"])
    lines.append("")
    lines.append(" ".join(HASHTAGS))

    return "\n".join(lines)


def upload_photo(page_id, token, url):

    endpoint = f"{GRAPH_BASE}/{page_id}/photos"

    data = {
        "url": url,
        "published": "false",
        "access_token": token
    }

    r = requests.post(endpoint, data=data)

    j = r.json()

    if "error" in j:
        raise SystemExit(j)

    return j["id"]


def create_post(page_id, token, photos, caption):

    endpoint = f"{GRAPH_BASE}/{page_id}/feed"

    attached = []

    for p in photos:
        attached.append({"media_fbid": p})

    data = {
        "message": caption,
        "attached_media": json.dumps(attached),
        "access_token": token
    }

    r = requests.post(endpoint, data=data)

    j = r.json()

    if "error" in j:
        raise SystemExit(j)

    return j


def main():

    page_id = env("PAGE_ID")
    token = env("PAGE_ACCESS_TOKEN")
    csv_url = env("SHOPEE_CSV_URL")

    print("Fetching CSV...")

    text = fetch_csv(csv_url)

    products = parse_products(text)

    print("Products:", len(products))

    state = load_state()

    posted = set(state["posted"])

    candidates = [p for p in products if p["key"] not in posted]

    if not candidates:
        candidates = products
        state["posted"] = []

    product = random.choice(candidates)

    print("Selected:", product["name"])

    caption = build_caption(product)

    imgs = product["images"][:POST_IMAGES_COUNT]

    photo_ids = []

    for img in imgs:
        print("Uploading image")
        pid = upload_photo(page_id, token, img)
        photo_ids.append(pid)
        time.sleep(1)

    print("Creating post")

    post = create_post(page_id, token, photo_ids, caption)

    print("Posted:", post)

    state["posted"].append(product["key"])

    save_state(state)


if __name__ == "__main__":
    main()
