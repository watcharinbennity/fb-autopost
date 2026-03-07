import requests
import json
import random

KEYWORDS = [
    "ไฟโซล่า",
    "ปลั๊กไฟ",
    "เครื่องมือช่าง",
    "สว่านไร้สาย",
    "หลอดไฟ LED"
]

def search_shopee(keyword):

    url = f"https://shopee.co.th/api/v4/search/search_items?keyword={keyword}&limit=20"

    r = requests.get(url)

    data = r.json()

    products = []

    for item in data["items"]:

        i = item["item_basic"]

        products.append({
            "name": i["name"],
            "category": "tools",
            "rating": i.get("item_rating",{}).get("rating_star",4),
            "sold": i.get("historical_sold",0),
            "link": f"https://shopee.co.th/product/{i['shopid']}/{i['itemid']}"
        })

    return products


def update_products():

    all_products = []

    for k in KEYWORDS:

        try:
            items = search_shopee(k)
            all_products.extend(items)
        except:
            pass

    random.shuffle(all_products)

    with open("products.json","w",encoding="utf-8") as f:
        json.dump(all_products,f,ensure_ascii=False,indent=2)


if __name__ == "__main__":
    update_products()
