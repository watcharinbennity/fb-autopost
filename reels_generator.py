import json
import random

def load_reels():

    try:
        with open("reels_ideas_100.json",encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def generate_reels():

    reels=load_reels()

    idea=random.choice(reels)

    script=f"""
🎬 Reel Idea

Hook:
{idea['hook']}

Content:
{idea['idea']}

CTA:
ดูสินค้าในคอมเมนต์
"""

    with open("reels_script.txt","w",encoding="utf-8") as f:
        f.write(script)

    return script
