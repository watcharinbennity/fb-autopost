import random
from ai_engine import ask_ai

TOPICS=[
"ของใช้ไฟฟ้าที่ควรมีติดบ้าน",
"เครื่องมือช่างที่ควรมี",
"ปลั๊กไฟแบบไหนปลอดภัย",
"ของใช้ไฟฟ้าที่ช่วยประหยัดไฟ"
]

QUESTIONS=[
"บ้านคุณใช้ปลั๊กไฟกี่ตัว",
"บ้านคุณใช้หลอดไฟสีอะไร",
"เครื่องมือช่างที่ใช้บ่อยที่สุดคืออะไร"
]


def viral_post():

    topic=random.choice(TOPICS)

    prompt=f"""
เขียนโพสต์ Facebook ให้ไวรัล

หัวข้อ {topic}

สั้น
มี emoji
ชวนคอมเมนต์
"""

    return ask_ai(prompt)


def engagement_post():

    q=random.choice(QUESTIONS)

    return f"""
💬 มาคุยกันหน่อย

{q}

คอมเมนต์หน่อย
"""
