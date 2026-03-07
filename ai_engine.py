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


def product_caption(product):

    prompt=f"""
เขียนโพสต์ Facebook ขายสินค้า

สินค้า {product['name']}
ราคา {product['price']}
รีวิว {product['rating']}
ขายแล้ว {product['sold']}

สั้น กระตุ้นซื้อ
"""

    return ask_ai(prompt)


def viral_text(topic):

    prompt=f"""
เขียนโพสต์ Facebook แบบไวรัล

หัวข้อ {topic}

สั้น กระตุ้นคอมเมนต์
"""

    return ask_ai(prompt)


def reels_script(product):

    prompt=f"""
เขียน script reels 15 วินาที

สินค้า {product['name']}

Hook
โชว์สินค้า
Call to action
"""

    return ask_ai(prompt)
