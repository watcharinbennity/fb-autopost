import os
import json
import random
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

USE_OPENAI = os.getenv("USE_OPENAI", "true").lower() == "true"


def append_link(text, link):

    if link in text:
        return text

    return f"{text}\n\n🛒 สั่งซื้อสินค้า\n{link}"


def generate_caption(product):

    link = product["link"]

    if not USE_OPENAI or not OPENAI_API_KEY:

        base = f"""
สินค้าแนะนำสำหรับงานช่าง ⚡

{product['title']}

เหมาะสำหรับงานไฟฟ้า งานติดตั้ง
เช็กรายละเอียดที่ลิงก์ด้านล่าง
"""

        return append_link(base.strip(), link)

    prompt = f"""
เขียนแคปชัน Facebook ภาษาไทย

สินค้า:
{product['title']}

เงื่อนไข

เขียน 10 แบบ
ไม่ใส่ราคา
3-5 บรรทัด
โทนมืออาชีพ

ตอบ JSON

{{"captions":["1","2","3","4","5","6","7","8","9","10"]}}
"""

    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"}
        }
    )

    data = r.json()

    content = data["choices"][0]["message"]["content"]

    obj = json.loads(content)

    captions = obj.get("captions", [])

    caption = random.choice(captions)

    return append_link(caption, link)
