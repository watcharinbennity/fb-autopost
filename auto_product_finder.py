import json
import random

def load_products():

    try:
        with open("products.json",encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def find_trending_products():

    products=load_products()

    trending=[
        p for p in products
        if p.get("sold",0) > 100
        and p.get("rating",0) >= 4
    ]

    if not trending:
        return None

    return random.choice(trending)
