import os
import requests
import csv
import random
import json
import urllib.request

PAGE_ID = os.getenv("PAGE_ID")
ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")

if not PAGE_ID:
    raise Exception("Missing env: PAGE_ID")

if not ACCESS_TOKEN:
    raise Exception("Missing env: PAGE_ACCESS_TOKEN")

if not CSV_URL:
    raise Exception("Missing env: SHOPEE_CSV_URL")

# โหลด CSV
response = urllib.request.urlopen(CSV_URL)
lines = [l.decode("utf-8") for l in response.readlines()]
reader = csv.DictReader(lines)

posts = []
for row in reader:
    posts.append({
        "title": row.get("name",""),
        "image": row.get("image",""),
        "url": row.get("url","")
    })

# โหลด state
state_file = "state.json"
if os.path.exists(state_file):
    with open(state_file) as f:
        state = json.load(f)
else:
    state = {"index":0}

index = state["index"]

if index >= len(posts):
    index = 0

post = posts[index]

caption = f"""
{post['title']}

🛒 สั่งซื้อ:
{post['url']}

#BENHomeElectrical
"""

url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"

payload = {
    "url": post["image"],
    "caption": caption,
    "access_token": ACCESS_TOKEN
}

r = requests.post(url,data=payload)

print(r.text)

state["index"] = index + 1

with open(state_file,"w") as f:
    json.dump(state,f)
