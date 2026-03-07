import os
import requests

OPENAI_KEY = os.getenv("OPENAI_API_KEY")

def ask_ai(prompt):

    if not OPENAI_KEY:
        return None

    try:

        r=requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization":f"Bearer {OPENAI_KEY}",
                "Content-Type":"application/json"
            },
            json={
                "model":"gpt-4.1-mini",
                "input":prompt
            },
            timeout=20
        )

        data=r.json()

        return data["output"][0]["content"][0]["text"]

    except Exception as e:

        print("AI ERROR",e)

        return None


def generate_caption(product):

    prompt=f"""
เขียนแคปชั่นขายสินค้า Facebook

สินค้า: {product['name']}
ราคา: {product['price']}
รีวิว: {product['rating']}
ขายแล้ว: {product['sold']}

โพสต์สั้น
มี emoji
ชวนซื้อ
"""

    return ask_ai(prompt)
