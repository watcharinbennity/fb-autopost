import os
import requests

OPENAI=os.getenv("OPENAI_API_KEY")

def ask_ai(prompt):

    if not OPENAI:
        return None

    try:

        r=requests.post(
        "https://api.openai.com/v1/responses",
        headers={
        "Authorization":f"Bearer {OPENAI}",
        "Content-Type":"application/json"
        },
        json={
        "model":"gpt-4.1-mini",
        "input":prompt
        },
        timeout=15
        )

        data=r.json()

        return data["output"][0]["content"][0]["text"]

    except:

        return None


def ai_caption(product):

    prompt=f"""
เขียนโพสต์ Facebook ขายสินค้า

สินค้า {product['name']}
ราคา {product['price']}
รีวิว {product['rating']}
ขายแล้ว {product['sold']}

สั้น กระตุ้นซื้อ
"""

    return ask_ai(prompt)
