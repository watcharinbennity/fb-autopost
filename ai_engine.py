import os
import requests

OPENAI_KEY = os.getenv("OPENAI_API_KEY")

def ask_ai(prompt):

    if not OPENAI_KEY:
        return None

    try:

        r = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4.1-mini",
                "input": prompt
            },
            timeout=30
        )

        data = r.json()

        return data["output"][0]["content"][0]["text"]

    except:
        return None


def choose_product(products):

    text = "\n".join([
        f"{p['name']} | rating:{p['rating']} | sold:{p['sold']} | price:{p['price']}"
        for p in products[:20]
    ])

    prompt = f"""
เลือกสินค้า 1 ตัวที่มีโอกาสขายดีที่สุดสำหรับเพจเครื่องมือช่าง

{text}

ตอบชื่อสินค้าอย่างเดียว
"""

    result = ask_ai(prompt)

    if result:

        for p in products:
            if p["name"] in result:
                return p

    return products[0]


def generate_caption(product):

    prompt = f"""
เขียนโพสต์ Facebook สำหรับขายสินค้า

สินค้า: {product['name']}
ราคา: {product['price']} บาท
รีวิว: {product['rating']}
ขายแล้ว: {product['sold']}

เงื่อนไข

- ภาษาไทย
- ไม่เกิน 5 บรรทัด
- มี emoji
- แนวขายของ
"""

    return ask_ai(prompt)
