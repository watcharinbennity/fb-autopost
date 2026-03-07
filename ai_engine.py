import os
import requests

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
TIMEOUT = 20


def ask_ai(prompt: str):
    if not OPENAI_KEY:
        return None

    try:
        r = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4.1-mini",
                "input": prompt,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        return data["output"][0]["content"][0]["text"].strip()
    except Exception as e:
        print(f"AI ERROR: {e}", flush=True)
        return None


def choose_product(products: list[dict]):
    if not products:
        return None

    shortlist = products[:10]
    text = "\n".join(
        f"{p['name']} | rating:{p['rating']} | sold:{p['sold']} | price:{p['price']}"
        for p in shortlist
    )

    prompt = f"""
เลือกสินค้า 1 ตัวที่เหมาะกับเพจ BEN Home & Electrical มากที่สุด
เน้นของใช้ในบ้าน อุปกรณ์ไฟฟ้า เครื่องมือช่าง DIY
ให้ดูจากความน่าขาย ความตรงหมวด และความน่าเชื่อถือ

รายการ:
{text}

ตอบชื่อสินค้าอย่างเดียว
""".strip()

    result = ask_ai(prompt)
    if result:
        for p in shortlist:
            if p["name"] and p["name"] in result:
                return p

    return shortlist[0]


def generate_caption(product: dict):
    prompt = f"""
เขียนแคปชั่นขายสินค้า Facebook ภาษาไทย สำหรับเพจ BEN Home & Electrical

สินค้า: {product['name']}
ราคา: {product['price']} บาท
รีวิว: {product['rating']}
ขายแล้ว: {product['sold']}

กติกา:
- ไม่เกิน 5 บรรทัด
- มี emoji พอดี
- โทนน่าเชื่อถือ
- ชวนกดซื้อ
- ยังไม่ต้องใส่ลิงก์
""".strip()

    return ask_ai(prompt)
