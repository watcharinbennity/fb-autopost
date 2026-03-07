import os
import requests

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
TIMEOUT = 20


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
            timeout=TIMEOUT
        )
        r.raise_for_status()
        data = r.json()
        return data["output"][0]["content"][0]["text"].strip()
    except Exception as e:
        print(f"AI ERROR: {e}", flush=True)
        return None


def choose_product(products):
    if not products:
        return None

    text = "\n".join([
        f"{p['name']} | rating:{p['rating']} | sold:{p['sold']} | price:{p['price']}"
        for p in products[:10]
    ])

    prompt = f"""
เลือกสินค้า 1 ตัวที่มีโอกาสขายดีที่สุดสำหรับเพจ BEN Home & Electrical

{text}

ตอบชื่อสินค้าอย่างเดียว
"""

    result = ask_ai(prompt)

    if result:
        for p in products:
            if p["name"] and p["name"] in result:
                return p

    return products[0]


def generate_caption(product):
    prompt = f"""
เขียนโพสต์ Facebook ภาษาไทยสำหรับขายสินค้า

สินค้า: {product['name']}
ราคา: {product['price']} บาท
รีวิว: {product['rating']}
ขายแล้ว: {product['sold']}

เงื่อนไข:
- ไม่เกิน 5 บรรทัด
- มี emoji พอดี
- โทนน่าเชื่อถือ
- ยังไม่ต้องใส่ลิงก์
"""

    return ask_ai(prompt)
