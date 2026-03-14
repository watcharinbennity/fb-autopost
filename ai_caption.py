import os
import random
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

FALLBACK_CAPTIONS = [
    "งานไฟ งานช่าง งานติดตั้ง ต้องมีตัวช่วยดี ๆ 👨‍🔧⚡\n{title}\n\nเหมาะกับสายช่างและคนที่ชอบทำงานเองที่บ้าน\nเช็กรายละเอียดล่าสุดที่ลิงก์ด้านล่าง",
    "ไอเท็มสายไฟฟ้า/เครื่องมือที่น่าใช้ 🔧⚡\n{title}\n\nใช้งานสะดวก เหมาะทั้งงานบ้านและงานช่าง\nเช็กรายละเอียดล่าสุดที่ลิงก์ด้านล่าง",
    "ของดีสาย BEN Home & Electrical ⚡\n{title}\n\nคัดมาให้แล้วสำหรับสายไฟ สายช่าง สายติดตั้ง\nเช็กรายละเอียดล่าสุดที่ลิงก์ด้านล่าง",
    "ตัวช่วยงานช่างที่น่าสนใจ 👷‍♂️\n{title}\n\nดูใช้งานง่าย น่ามีติดบ้านติดร้านไว้\nเช็กรายละเอียดล่าสุดที่ลิงก์ด้านล่าง",
]


def fallback_caption(product):
    return random.choice(FALLBACK_CAPTIONS).format(title=product["title"])


def generate_caption(product):
    if not OPENAI_API_KEY:
        return fallback_caption(product)

    prompt = f"""
เขียนแคปชัน Facebook ภาษาไทย สำหรับเพจ BEN Home & Electrical

สินค้า:
{product['title']}

เงื่อนไข:
- ไม่ใส่ราคาตัวเลข
- ความยาว 3-5 บรรทัด
- โทนมืออาชีพ อ่านง่าย
- เหมาะกับสายไฟฟ้า เครื่องมือช่าง งานติดตั้ง
- ปิดท้ายให้ชวนกดดูรายละเอียดที่ลิงก์ด้านล่าง
- ขอแค่ข้อความแคปชันอย่างเดียว
""".strip()

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": "คุณเป็นนักเขียนแคปชันขายของภาษาไทยเก่งด้านสินค้าไฟฟ้าและเครื่องมือช่าง"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.9,
            },
            timeout=90,
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return fallback_caption(product)
