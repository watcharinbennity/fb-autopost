import random
from ai_engine import ask_ai

VIRAL_TOPICS = [
"ของใช้ไฟฟ้าที่ควรมีติดบ้าน",
"เครื่องมือช่างราคาถูกแต่ดี",
"อุปกรณ์ไฟฟ้าที่ช่วยให้ชีวิตง่ายขึ้น",
"ของใช้ในบ้านที่คนส่วนใหญ่ยังไม่รู้",
"อุปกรณ์ไฟฟ้าที่ควรมีติดบ้าน",
"เครื่องมือช่างที่ควรมีติดบ้าน",
"ปลั๊กไฟแบบไหนปลอดภัย",
"ไฟโซลาร์ดีไหม",
"ของใช้ไฟฟ้าราคาถูกจาก Shopee",
"อุปกรณ์ที่ช่วยประหยัดค่าไฟ"
]

ENGAGEMENT_POSTS = [
"บ้านคุณใช้ปลั๊กไฟกี่ตัว",
"เครื่องมือช่างที่ใช้บ่อยที่สุดคืออะไร",
"บ้านคุณใช้หลอดไฟสีอะไร",
"ของใช้ไฟฟ้าที่ขาดไม่ได้คืออะไร"
]


def viral_topic():
    return random.choice(VIRAL_TOPICS)


def engagement_question():
    return random.choice(ENGAGEMENT_POSTS)


def generate_viral_post():

    topic = viral_topic()

    prompt = f"""
เขียนโพสต์ Facebook ให้ไวรัล

หัวข้อ: {topic}

กติกา

โพสต์สั้น
อ่านง่าย
มี emoji
ชวนคอมเมนต์
"""

    return ask_ai(prompt)


def generate_engagement_post():

    question = engagement_question()

    return f"""
💬 มาคุยกันหน่อย

{question}

คอมเมนต์บอกหน่อย
"""
