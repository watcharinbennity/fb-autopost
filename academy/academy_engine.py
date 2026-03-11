import json
import os
import requests
from academy_topics import CURRICULUM
from video_builder import build_intro_reel

OPENAI_KEY = os.environ["OPENAI_API_KEY"]
PAGE_ID = os.environ["PAGE_ID"]
PAGE_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]

BASE_DIR = os.path.dirname(__file__)
STATE_PATH = os.path.join(BASE_DIR, "state.json")
MASCOT_PATH = os.path.join(BASE_DIR, "assets", "chang_ben.png")


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    return {
        "initialized": False,
        "module_index": 0,
        "topic_index": 0,
    }


def save_state(data):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def openai_chat(prompt: str) -> str:

    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        },
        timeout=60,
    )

    r.raise_for_status()

    return r.json()["choices"][0]["message"]["content"]


def tts_to_mp3(text: str):

    r = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini-tts",
            "voice": "alloy",
            "input": text,
        },
        timeout=180,
    )

    r.raise_for_status()

    with open("intro.mp3", "wb") as f:
        f.write(r.content)

    return "intro.mp3"


# ---------------------------
# FACEBOOK REEL UPLOAD
# ---------------------------

def upload_reel(video_path, caption):

    start_url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/video_reels"

    start_res = requests.post(
        start_url,
        data={
            "upload_phase": "start",
            "access_token": PAGE_TOKEN,
        },
    )

    start_res.raise_for_status()

    start_data = start_res.json()

    print("START:", start_data, flush=True)

    video_id = start_data["video_id"]
    upload_url = start_data["upload_url"]

    # อ่านไฟล์ video เป็น binary
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    upload_res = requests.post(
        upload_url,
        data=video_bytes,
        headers={
            "Authorization": f"OAuth {PAGE_TOKEN}",
            "Content-Type": "application/octet-stream",
        },
    )

    print("UPLOAD:", upload_res.status_code, upload_res.text, flush=True)

    upload_res.raise_for_status()

    finish_res = requests.post(
        start_url,
        data={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": caption,
            "access_token": PAGE_TOKEN,
        },
    )

    print("FINISH:", finish_res.status_code, finish_res.text, flush=True)

    finish_res.raise_for_status()

    return finish_res.json()

def create_intro_caption():

    return (
        "⚡ เปิดตัว BEN Home & Electrical Academy\n\n"
        "สวัสดีครับ ผมช่างเบน\n"
        "จากนี้เราจะเรียนไฟฟ้ากันตั้งแต่พื้นฐาน จนถึงระดับวิศวกร\n"
        "ติดตามไว้ แล้วเรียนไปด้วยกันครับ"
    )


# ---------------------------
# FIRST INTRO REEL
# ---------------------------

def run_first_intro():

    narration = (
        "สวัสดีครับ ผมช่างเบน จาก BEN Home and Electrical "
        "จากนี้เราจะเรียนไฟฟ้ากันตั้งแต่พื้นฐาน "
        "จนถึงระดับวิศวกร"
    )

    audio_path = tts_to_mp3(narration)

    video_path = build_intro_reel(
        mascot_path=MASCOT_PATH,
        audio_path=audio_path,
        out_path="intro_final.mp4",
    )

    print("VIDEO CREATED:", video_path, flush=True)

    result = upload_reel(video_path, create_intro_caption())

    print("REEL RESULT:", result, flush=True)


# ---------------------------
# NEXT TOPIC
# ---------------------------

def get_next_topic():

    state = load_state()

    m = state["module_index"]
    t = state["topic_index"]

    module = CURRICULUM[m]
    topic = module["topics"][t]

    state["topic_index"] += 1

    if state["topic_index"] >= len(module["topics"]):
        state["topic_index"] = 0
        state["module_index"] += 1

    if state["module_index"] >= len(CURRICULUM):
        state["module_index"] = 0

    save_state(state)

    return module["module"], topic


# ---------------------------
# GENERATE KNOWLEDGE POST
# ---------------------------

def generate_knowledge_post(module_name, topic):

    prompt = f"""
เขียนโพสต์ความรู้ไฟฟ้า

หัวข้อ: {topic}
หมวด: {module_name}

อธิบายเข้าใจง่าย
ยกตัวอย่างจริง
ความยาวประมาณ 300 คำ
"""

    try:
        return openai_chat(prompt)

    except Exception:

        return f"""
⚡ {topic}

ช่างเบนจะพาเรียนเรื่อง {topic}

เนื้อหานี้เป็นพื้นฐานสำคัญของงานไฟฟ้า
ถ้าเข้าใจหัวข้อนี้ จะต่อยอดเรื่องอื่นได้ง่าย

#BENHomeAndElectrical
"""


# ---------------------------
# MAIN
# ---------------------------

def main():

    state = load_state()

    # FIRST RUN
    if not state.get("initialized", False):

        run_first_intro()

        state["initialized"] = True
        save_state(state)

        return

    # NEXT POSTS

    module_name, topic = get_next_topic()

    print("POST:", module_name, topic, flush=True)

    text = generate_knowledge_post(module_name, topic)

    result = publish_text_post(text)

    print("POST RESULT:", result, flush=True)


if __name__ == "__main__":
    main()
