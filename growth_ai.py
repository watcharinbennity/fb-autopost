import random
import json

LOG_FILE="post_log.json"

def load_log():

    try:
        with open(LOG_FILE,"r",encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def analyze():

    logs=load_log()

    stats={}

    for l in logs:

        t=l.get("type","unknown")

        stats[t]=stats.get(t,0)+1

    return stats


def ai_caption(name):

    captions=[

    f"⚡ {name}\n\nของดีที่ควรมีติดบ้าน",
    f"🔥 {name}\n\nใครใช้อยู่บ้าง",
    f"🛠 {name}\n\nของมันต้องมี",
    f"⚡ {name}\n\nแนะนำเลยตัวนี้",
    f"🔥 {name}\n\nของดีราคาคุ้ม"

    ]

    return random.choice(captions)


def reels_idea():

    ideas=[

    "รีวิวไฟโซล่ากลางคืน",
    "ปลั๊กไฟแบบไหนปลอดภัย",
    "เครื่องมือช่างที่ควรมีติดบ้าน",
    "หลอดไฟ LED ประหยัดไฟไหม",
    "รีวิวสว่านไร้สาย"

    ]

    return random.choice(ideas)
