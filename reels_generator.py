import json
import random

REELS_FILE = "reels_ideas_100.json"
OUTPUT_FILE = "reels_script.txt"


def load_reels():
    try:
        with open(REELS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def generate_reels():
    reels = load_reels()

    if reels:
        idea = random.choice(reels)
        hook = idea.get("hook", "ของดีที่ควรมีติดบ้าน")
        content = idea.get("idea", "อธิบายข้อดีสั้น ๆ และปิดด้วย call to action")
    else:
        hook = "ของดีที่ควรมีติดบ้าน"
        content = "อธิบายข้อดีสั้น ๆ และปิดด้วย call to action"

    script = f"""🎬 REELS IDEA

Hook:
{hook}

Content:
{content}

CTA:
ดูสินค้าในคอมเมนต์
"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(script)

    return script
