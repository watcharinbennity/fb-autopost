import os
import requests

OPENAI_KEY = os.getenv("OPENAI_API_KEY")


def ai_choose_product(products):

    if not OPENAI_KEY:
        return products[0]

    text = "\n".join([
        f"{p['name']} | rating:{p['rating']} | sold:{p['sold']} | price:{p['price']}"
        for p in products[:20]
    ])

    prompt = f"""
เลือกสินค้า 1 ตัวที่มีโอกาสขายดีที่สุดสำหรับเพจขายเครื่องมือช่าง

รายการสินค้า

{text}

ตอบแค่ชื่อสินค้า
"""

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

        answer = data["output"][0]["content"][0]["text"]

        for p in products:
            if p["name"] in answer:
                return p

    except Exception:
        pass

    return products[0]


def ai_caption(product):

    if not OPENAI_KEY:
        return None

    prompt = f"""
เขียนแคปชั่นขายสินค้า Facebook

สินค้า: {product['name']}
ราคา: {product['price']} บาท
รีวิว: {product['rating']}
ขายแล้ว: {product['sold']}

เงื่อนไข

- ภาษาไทย
- 5 บรรทัด
- มี emoji
- สำหรับเพจเครื่องมือช่าง
"""

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
