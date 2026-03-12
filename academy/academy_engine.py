# academy/academy_engine.py

import json
import os
import requests

from academy_topics import CURRICULUM
from diagram_generator import draw_for_topic
from video_builder import build_video_from_image, merge_audio, cleanup_temp

OPENAI_KEY = os.environ["OPENAI_API_KEY"]
PAGE_ID = os.environ["PAGE_ID"]
PAGE_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]

BASE_DIR = os.path.dirname(__file__)
STATE_FILE = os.path.join(BASE_DIR, "state.json")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"initialized": False, "episode": 0}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


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


def tts_to_mp3(text: str, out_path: str = "lesson.mp3") -> str:
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
            "instructions": "พูดภาษาไทยแบบธรรมชาติ ชัดเจน มีพลัง นุ่มลึก สไตล์พากย์หนังจีน จังหวะไม่เร็วเกินไป"
        },
        timeout=180,
    )
    r.raise_for_status()

    with open(out_path, "wb") as f:
        f.write(r.content)

    return out_path


def upload_video(video_path: str, caption: str):
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/videos"

    with open(video_path, "rb") as f:
        files = {"source": f}
        data = {
            "description": caption,
            "title": "BEN Home & Electrical Academy",
            "published": "true",
            "access_token": PAGE_TOKEN,
        }
        r = requests.post(url, files=files, data=data, timeout=300)

    print("VIDEO UPLOAD STATUS:", r.status_code, flush=True)
    print("VIDEO UPLOAD BODY:", r.text, flush=True)

    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"VIDEO UPLOAD ERROR: {data}")
    return data


def publish_text_post(message: str):
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    r = requests.post(
        url,
        data={
            "message": message,
            "access_token": PAGE_TOKEN,
        },
        timeout=60,
    )

    print("TEXT POST STATUS:", r.status_code, flush=True)
    print("TEXT POST BODY:", r.text, flush=True)

    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"TEXT POST ERROR: {data}")
    return data


def build_intro_script():
    return {
        "title": "EP1 เปิดตัวช่างเบน",
        "caption": (
            "⚡ เปิดตัว BEN Home & Electrical Academy\n\n"
            "สวัสดีครับ ผมช่างเบน\n"
            "จากนี้เราจะเรียนไฟฟ้ากันตั้งแต่พื้นฐาน จนถึงระดับวิศวกร\n"
            "เรียนแบบเข้าใจง่าย ใช้ได้จริง และค่อย ๆ ไต่ระดับไปด้วยกันครับ"
        ),
        "narration": (
            "สวัสดีครับ ผมช่างเบน จาก BEN Home and Electrical. "
            "จากนี้เราจะเรียนไฟฟ้ากัน ตั้งแต่พื้นฐาน ไปจนถึงระดับวิศวกร. "
            "เรียนแบบเข้าใจง่าย ใช้ได้จริง และค่อย ๆ ไต่ระดับไปด้วยกันครับ."
        ),
        "image_type": "concept"
    }


def build_lesson(topic_obj: dict, episode_no: int) -> dict:
    prompt = f"""
ช่วยเขียนเนื้อหาสำหรับคลิปสอนไฟฟ้าภาษาไทย

หัวข้อ: {topic_obj['title']}
หมวด: {topic_obj['module']}
ตอนที่: EP{episode_no}

ต้องการผลลัพธ์เป็น JSON เท่านั้น รูปแบบ:
{{
  "title": "EP{episode_no} ...",
  "hook": "...",
  "explain": "...",
  "summary": "...",
  "caption": "..."
}}

เงื่อนไข:
- สอนจากง่ายไปยาก
- อธิบายให้คนทั่วไปเข้าใจ
- ไม่ใส่ลิงก์ขาย
- ไม่ใส่ราคา
- เนื้อหาแน่นแต่กระชับ
- สรุปท้ายให้จำง่าย
- ใช้คำว่า ช่างเบน
"""
    fallback = {
        "title": f"EP{episode_no} {topic_obj['title']}",
        "hook": f"วันนี้ช่างเบนจะพาเข้าใจเรื่อง {topic_obj['title']} แบบง่าย ๆ",
        "explain": f"{topic_obj['title']} เป็นพื้นฐานสำคัญของงานไฟฟ้า ถ้าเข้าใจเรื่องนี้ จะต่อยอดเรื่องอื่นได้ง่ายขึ้น",
        "summary": f"สรุปสั้น ๆ: {topic_obj['title']} คือเรื่องสำคัญที่ต้องเข้าใจก่อนขึ้นระดับต่อไป",
        "caption": f"⚡ EP{episode_no} {topic_obj['title']}\nช่างเบนสอนไฟฟ้า | BEN Home & Electrical"
    }

    try:
        raw = openai_chat(prompt)
        return json.loads(raw)
    except Exception as e:
        print("OPENAI LESSON ERROR:", e, flush=True)
        return fallback


def run_intro():
    intro = build_intro_script()

    image_path = "intro.png"
    silent_video = "intro_silent.mp4"
    audio_path = "intro.mp3"
    final_video = "intro_final.mp4"

    draw_for_topic(intro["image_type"], image_path, intro["title"])
    build_video_from_image(image_path, silent_video, duration=18)
    tts_to_mp3(intro["narration"], audio_path)
    merge_audio(silent_video, audio_path, final_video)

    result = upload_video(final_video, intro["caption"])
    cleanup_temp([image_path, silent_video, audio_path, final_video])
    return result


def run_lesson(episode_no: int):
    if episode_no >= len(CURRICULUM):
        episode_no = 0

    topic = CURRICULUM[episode_no]
    lesson = build_lesson(topic, episode_no + 1)

    # โพสต์ความรู้เป็นข้อความหลังคลิปเปิดตัว
    message = (
        f"{lesson['title']}\n\n"
        f"{lesson['hook']}\n\n"
        f"{lesson['explain']}\n\n"
        f"{lesson['summary']}\n\n"
        f"#ช่างเบน #BENHomeAndElectrical #ไฟฟ้า"
    )
    return publish_text_post(message)


def main():
    state = load_state()

    # ครั้งแรกโพสต์คลิปเปิดตัว
    if not state.get("initialized", False):
        result = run_intro()
        if result.get("id") or result.get("video_id"):
            state["initialized"] = True
            state["episode"] = 0
            save_state(state)
            print("STATE UPDATED: intro posted", flush=True)
            return
        raise RuntimeError(f"Intro post failed: {result}")

    # ครั้งถัดไปโพสต์ความรู้ตามลำดับ
    ep = state.get("episode", 0)
    result = run_lesson(ep)

    if result.get("id"):
        state["episode"] = ep + 1
        if state["episode"] >= len(CURRICULUM):
            state["episode"] = 0
        save_state(state)
        print(f"STATE UPDATED: episode={state['episode']}", flush=True)
        return

    raise RuntimeError(f"Lesson post failed: {result}")


if __name__ == "__main__":
    main()
