import os
import requests

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
TIMEOUT = 15


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
        f"{i+1}. {p['name']} | rating:{p['rating']} | sold:{p['sold']} | price:{p['price']} | score:{p['final_score']}"
        for i, p in enumerate(shortlist)
    )

    prompt = f"""
เลือกสินค้า 1 ตัวที่เหมาะกับเพจ BEN Home & Electrical มากที่สุด
เน้นของใช้ในบ้าน อุปกรณ์ไฟฟ้า เครื่องมือช่าง DIY
ดูจากความตรงหมวด ความน่าขาย และความคุ้มราคา

รายการ:
{text}

ตอบเป็นเลขข้อเดียว เช่น 1 หรือ 2 หรือ 3
""".strip()

    result = ask_ai(prompt)

    if result:
        for i in range(len(shortlist)):
            if str(i + 1) in result:
                return shortlist[i]

    return shortlist[0]


def generate_caption_variants(product: dict):
    prompt = f"""
เขียนแคปชั่นขายสินค้า Facebook ภาษาไทย สำหรับเพจ BEN Home & Electrical
สินค้า: {product['name']}
ราคา: {product['price']} บาท
รีวิว: {product['rating']}
ขายแล้ว: {product['sold']}

เขียนมา 3 แบบ
แต่ละแบบไม่เกิน 5 บรรทัด
มี emoji พอดี
ชวนกดซื้อ
ยังไม่ต้องใส่ลิงก์

คั่นแต่ละแบบด้วย ----
""".strip()

    result = ask_ai(prompt)
    if not result:
        return None

    parts = [p.strip() for p in result.split("----") if p.strip()]
    return parts[:3] if parts else None


def choose_best_caption(product: dict, captions: list[str]):
    if not captions:
        return None
    if len(captions) == 1:
        return captions[0]

    text = "\n\n".join([f"{i+1}. {c}" for i, c in enumerate(captions)])

    prompt = f"""
เลือกแคปชั่นที่น่ากดที่สุดสำหรับโพสต์ Facebook ขายสินค้า
สินค้า: {product['name']}

ตัวเลือก:
{text}

ตอบเป็นเลขข้อเดียว เช่น 1 หรือ 2 หรือ 3
""".strip()

    result = ask_ai(prompt)

    if result:
        for i in range(len(captions)):
            if str(i + 1) in result:
                return captions[i]

    return captions[0]


def generate_best_caption(product: dict):
    captions = generate_caption_variants(product)
    return choose_best_caption(product, captions)


def viral_caption(topic: str):
    prompt = f"""
เขียนโพสต์ Facebook แบบไวรัล ภาษาไทย

หัวข้อ: {topic}

กติกา:
- สั้น
- มี emoji
- ชวนคอมเมนต์
- ไม่เกิน 4 บรรทัด
""".strip()

    return ask_ai(prompt)
