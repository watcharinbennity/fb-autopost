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


def tts_to_mp3(text: str, out_path: str = "intro.mp3") -> str:
    payload = {
        "model": "gpt-4o-mini-tts",
        "voice": "alloy",
        "input": text,
        "instructions": "พูดภาษาไทยแบบธรรมชาติ อบอุ่น มั่นใจ ชัดถ้อยชัดคำ เหมือนครูสอนไฟฟ้ามืออาชีพ จังหวะไม่เร็วเกินไป"
    }

    r = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    r.raise_for_status()

    with open(out_path, "wb") as f:
        f.write(r.content)

    return out_path


def upload_video_intro(video_path: str, caption: str):
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
    res = requests.post(
        url,
        data={
            "message": message,
            "access_token": PAGE_TOKEN,
        },
        timeout=30,
    )

    print("TEXT POST STATUS:", res.status_code, flush=True)
    print("TEXT POST BODY:", res.text, flush=True)

    res.raise_for_status()
    data = res.json()
    if "error" in data:
        raise RuntimeError(f"TEXT POST ERROR: {data}")
    return data


def create_intro_caption():
    return (
        "⚡ เปิดตัว BEN Home & Electrical Academy\n\n"
        "สวัสดีครับ ผมช่างเบน\n"
        "จากนี้เราจะเรียนไฟฟ้ากันตั้งแต่พื้นฐาน จนถึงระดับวิศวกร\n"
        "ติดตามไว้ แล้วเรียนไปด้วยกันครับ"
    )


def run_first_intro():
    narration = (
        "สวัสดีครับ ผมช่างเบน จาก เบน โฮม แอนด์ อิเล็กทริคอล. "
        "จากนี้เราจะเรียนไฟฟ้ากัน ตั้งแต่พื้นฐาน ไปจนถึงระดับวิศวกร. "
        "ผมจะสอนแบบเข้าใจง่าย ใช้ได้จริง และเรียนไปด้วยกันครับ."
    )

    audio_path = tts_to_mp3(narration, "intro.mp3")
    video_path = build_intro_reel(
        mascot_path=MASCOT_PATH,
        audio_path=audio_path,
        out_path="intro_final.mp4",
    )

    print("VIDEO CREATED:", video_path, flush=True)
    print("MASCOT EXISTS:", os.path.exists(MASCOT_PATH), MASCOT_PATH, flush=True)

    result = upload_video_intro(video_path, create_intro_caption())
    print("INTRO VIDEO RESULT:", result, flush=True)
    return result


def get_next_topic_preview(state):
    m = state["module_index"]
    t = state["topic_index"]

    if m >= len(CURRICULUM):
        m = 0
        t = 0

    module = CURRICULUM[m]
    topics = module["topics"]

    if t >= len(topics):
        m += 1
        t = 0
        if m >= len(CURRICULUM):
            m = 0
        module = CURRICULUM[m]
        topics = module["topics"]

    return m, t, module["module"], topics[t]


def advance_topic_pointer(state):
    m = state["module_index"]
    t = state["topic_index"]

    module = CURRICULUM[m]
    t += 1

    if t >= len(module["topics"]):
        t = 0
        m += 1

    if m >= len(CURRICULUM):
        m = 0

    state["module_index"] = m
    state["topic_index"] = t
    return state


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
    except Exception as e:
        print("OPENAI CHAT ERROR:", e, flush=True)
        return fallback


def main():
    state = load_state()

    if not state.get("initialized", False):
        result = run_first_intro()

        if result.get("id") or result.get("video_id"):
            state["initialized"] = True
            save_state(state)
            print("STATE UPDATED: initialized=True", flush=True)
            return
        raise RuntimeError(f"Intro video did not return publish id: {result}")

    m, t, module_name, topic = get_next_topic_preview(state)
    print(f"POST TOPIC: {module_name} - {topic}", flush=True)

    post_text = generate_knowledge_post(module_name, topic)
    result = publish_text_post(post_text)
    print("TEXT POST RESULT:", result, flush=True)

    if result.get("id"):
        state = advance_topic_pointer(state)
        save_state(state)
        print("STATE UPDATED: topic advanced", flush=True)
    else:
        raise RuntimeError(f"Text post did not return id: {result}")


if __name__ == "__main__":
    main()
