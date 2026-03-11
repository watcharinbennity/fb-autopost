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


def tts_to_mp3(text: str, out_path: str = "speech.mp3") -> str:
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

    with open(out_path, "wb") as f:
        f.write(r.content)

    return out_path


def upload_reel(video_path: str, caption: str):
    start_url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/video_reels"

    start_res = requests.post(
        start_url,
        data={
            "upload_phase": "start",
            "access_token": PAGE_TOKEN,
        },
        timeout=30,
    )
    start_res.raise_for_status()
    start_data = start_res.json()

    video_id = start_data.get("video_id")
    upload_url = start_data.get("upload_url")

    if not video_id or not upload_url:
        raise RuntimeError(f"Reel start failed: {start_data}")

    with open(video_path, "rb") as f:
        upload_res = requests.post(
            upload_url,
            data=f,
            headers={"Authorization": f"OAuth {PAGE_TOKEN}"},
            timeout=300,
        )
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
        timeout=60,
    )
    finish_res.raise_for_status()
    return finish_res.json()


def publish_text_post(message: str):
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    res = requests.post(
        url,
        data={
            "message": message,
            "access_token": PAGE_TOKEN,
        },
        timeout=30,
    )
    res.raise_for_status()
    return res.json()


def create_intro_caption():
    return (
        "⚡ เปิดตัว BEN Home & Electrical Academy\n\n"
        "สวัสดีครับ ผมช่างเบน\n"
        "จากนี้เราจะเรียนไฟฟ้ากันตั้งแต่พื้นฐาน จนถึงระดับวิศวกร\n"
        "ติดตามไว้ แล้วเรียนไปด้วยกันครับ"
    )


def run_first_intro():
    narration = (
        "สวัสดีครับ ผมช่างเบน จาก BEN Home & Electrical. "
        "จากนี้เราจะเรียนไฟฟ้ากันตั้งแต่พื้นฐาน ไปจนถึงระดับวิศวกร. "
        "ผมจะสอนแบบเข้าใจง่าย ใช้ได้จริง และเรียนไปด้วยกันครับ"
    )

    audio_path = tts_to_mp3(narration, "intro.mp3")
    video_path = build_intro_reel(
        mascot_path=MASCOT_PATH,
        audio_path=audio_path,
        out_path="academy_intro_final.mp4",
    )

    result = upload_reel(video_path, create_intro_caption())
    print("INTRO REEL RESULT:", result, flush=True)


def get_next_topic():
    state = load_state()
    m_idx = state["module_index"]
    t_idx = state["topic_index"]

    if m_idx >= len(CURRICULUM):
        m_idx = 0
        t_idx = 0

    module = CURRICULUM[m_idx]
    topics = module["topics"]

    if t_idx >= len(topics):
        m_idx += 1
        t_idx = 0
        if m_idx >= len(CURRICULUM):
            m_idx = 0
        module = CURRICULUM[m_idx]
        topics = module["topics"]

    topic = topics[t_idx]

    # advance pointer
    state["module_index"] = m_idx
    state["topic_index"] = t_idx + 1
    save_state(state)

    return module["module"], topic


def generate_knowledge_post(module_name: str, topic: str) -> str:
    prompt = f"""
ช่วยเขียนโพสต์ความรู้ไฟฟ้าภาษาไทย สำหรับเพจ BEN Home & Electrical

หัวข้อ: {topic}
หมวด: {module_name}

เงื่อนไข:
- อธิบายละเอียดแบบคนทั่วไปเข้าใจ
- เริ่มจากนิยามง่าย ๆ
- ยกตัวอย่างในชีวิตจริง
- ปิดท้ายด้วยสรุปสั้น ๆ
- ใช้ภาษาง่าย แต่เนื้อหาแน่น
- ความยาวประมาณ 250-500 คำ
- มีชื่อ "ช่างเบน" ในโพสต์
- จัดรูปแบบให้อ่านง่ายบน Facebook

ขอผลลัพธ์เป็นโพสต์พร้อมลง Facebook ได้ทันที
""".strip()

    fallback = (
        f"⚡ {topic}\n\n"
        f"ช่างเบนจะพาเรียนเรื่อง {topic} ในหมวด {module_name} แบบเข้าใจง่าย\n\n"
        f"เริ่มจากพื้นฐานก่อน: {topic} เป็นเรื่องสำคัญของงานไฟฟ้า เพราะใช้ต่อยอดไปยังระบบจริงได้\n\n"
        f"ลองนึกถึงการใช้งานในชีวิตประจำวัน เช่น ปลั๊กไฟ สวิตช์ หลอดไฟ หรือเครื่องใช้ไฟฟ้าในบ้าน "
        f"ทั้งหมดล้วนเกี่ยวข้องกับหลักการไฟฟ้านี้\n\n"
        f"สรุป: ถ้าเข้าใจ {topic} ได้ดี จะเรียนเรื่องไฟฟ้าระดับต่อไปง่ายขึ้นมาก\n\n"
        f"#ช่างเบน #BENHomeAndElectrical #ไฟฟ้า"
    )

    try:
        return openai_chat(prompt)
    except Exception:
        return fallback


def main():
    state = load_state()

    if not state.get("initialized", False):
        run_first_intro()
        state["initialized"] = True
        save_state(state)
        return

    module_name, topic = get_next_topic()
    print(f"POST TOPIC: {module_name} - {topic}", flush=True)

    post_text = generate_knowledge_post(module_name, topic)
    result = publish_text_post(post_text)
    print("TEXT POST RESULT:", result, flush=True)


if __name__ == "__main__":
    main()
