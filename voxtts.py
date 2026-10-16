"""
เสียงพากย์แบบเดียวกับคลิปสอนไฟฟ้าบน TikTok: VoxCPM (โคลนเสียงจาก assets/voice/ben_ref.ogg)
ผ่าน Hugging Face Space สาธารณะ แล้วตรวจคำที่พูดด้วย Whisper ภาษาไทย (ถอดเสียงกลับเป็นข้อความ)
- สร้างทีละท่อน ท่อนไหนถอดเสียงแล้วไม่ตรงบท จะสร้างใหม่ (สูงสุด VOX_TRIES ครั้ง) แล้วเลือกตัวที่ตรงที่สุด
- ถ้าท่อนไหนยังไม่ผ่านเกณฑ์ หรือเว็บล่ม คืน None ให้ระบบไปใช้เสียงสำรอง
"""
import json
import os
import re
import subprocess
import tempfile
import time
from typing import List, Optional, Tuple

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
VOX = os.getenv("VOX_SPACE", "https://openbmb-voxcpm-demo.hf.space").rstrip("/")
ASR = os.getenv("ASR_SPACE", "https://biodatlab-whisper-thai-demo.hf.space").rstrip("/")
REF_PATH = os.getenv("VOX_REF", os.path.join(HERE, "assets", "voice", "ben_ref.ogg"))
TRIES = int(os.getenv("VOX_TRIES", "3"))
MAX_CER = float(os.getenv("VOX_MAX_CER", "0.25"))  # ยอมให้ถอดเสียงคลาดได้ไม่เกิน 25% ของตัวอักษร
TEMPO = os.getenv("VOX_TEMPO", "1.0")
TIMEOUT = 240

# คำที่ VoxCPM อ่านไม่ชัด (เรียนรู้จากคลิป TikTok ตอน 1-01/1-02): เขียนบทเสียงให้อ่านถูก
SPEAK_FIX = [
    (re.compile(r"สรุป"), "สะหรุบ"),
    (re.compile(r"เหมือน(?!กับ)"), "เหมือนกับ"),
]
# คำที่เขียนแทนแล้ว ต้องแปลงกลับตอนเทียบผลถอดเสียง
CHECK_FIX = [("สะหรุบ", "สรุป")]


def log(*a):
    print("VOX:", *a, flush=True)


def speak_text(text: str) -> str:
    for rx, rep in SPEAK_FIX:
        text = rx.sub(rep, text)
    return text


def thai_only(s: str) -> str:
    for a, b in CHECK_FIX:
        s = s.replace(a, b)
    s = re.sub(r"[^฀-๿]", "", s)
    return s.replace("ๆ", "").replace("์", "")


def lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    return prev[len(b)]


def cer(expected: str, heard: str) -> float:
    e, h = thai_only(expected), thai_only(heard)
    if not e:
        return 0.0
    return lev(e, h) / len(e)


def split_lines(text: str, min_len: int = 18, max_len: int = 70) -> List[str]:
    """ตัดบทเป็นท่อนตามช่องว่าง (ภาษาไทยเว้นวรรคระหว่างประโยค) รวมท่อนสั้นเข้าด้วยกัน"""
    parts = [p for p in re.split(r"\s+", text.strip()) if p]
    out: List[str] = []
    for p in parts:
        if out and (len(out[-1]) < min_len or len(p) < 6) and len(out[-1]) + len(p) + 1 <= max_len:
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def call(base: str, api: str, data: list) -> list:
    r = requests.post(f"{base}/gradio_api/call/{api}", json={"data": data}, timeout=60)
    r.raise_for_status()
    eid = r.json()["event_id"]
    t = requests.get(f"{base}/gradio_api/call/{api}/{eid}", timeout=TIMEOUT).text
    if "event: complete" not in t:
        raise RuntimeError(t[-300:].replace("\n", " "))
    return json.loads(t.split("data: ")[-1])


def upload_ref() -> dict:
    with open(REF_PATH, "rb") as f:
        r = requests.post(f"{VOX}/gradio_api/upload", files={"files": ("ref.ogg", f, "audio/ogg")}, timeout=60)
    r.raise_for_status()
    return {"path": r.json()[0], "meta": {"_type": "gradio.FileData"}, "orig_name": "ref.ogg"}


def transcribe(url: str) -> str:
    try:
        res = call(ASR, "transcribe", [None, {"path": url, "url": url, "meta": {"_type": "gradio.FileData"},
                                              "orig_name": "a.mp3"}])
        return str(res[0])
    except Exception as e:
        log("ASR error:", str(e)[:200])
        return ""


def gen_line(line: str, ref: dict, work: str, idx: int) -> Tuple[Optional[str], float, str]:
    """คืน (ไฟล์เสียง, ค่าคลาดเคลื่อน, ข้อความที่ถอดได้) ของตัวที่ดีที่สุด"""
    best: Tuple[Optional[str], float, str] = (None, 9.0, "")
    settings = [(2, False), (2.5, True), (3, False)]
    for k in range(TRIES):
        cfg, norm = settings[k % len(settings)]
        try:
            g = call(VOX, "generate", [speak_text(line), "", ref, False, "", cfg, norm, False])
            url = g[0]["url"]
            path = os.path.join(work, f"l{idx}_{k}.wav")
            with open(path, "wb") as f:
                f.write(requests.get(url, timeout=120).content)
        except Exception as e:
            log(f"gen error line {idx} try {k}:", str(e)[:200])
            time.sleep(5)
            continue
        heard = transcribe(url)
        score = cer(line, heard) if heard else 0.5  # ASR ล่ม: ให้ผ่านแบบมีเงื่อนไข
        log(f"line {idx} try {k}: cer={score:.2f} | บท: {line} | ได้ยิน: {heard}")
        if score < best[1]:
            best = (path, score, heard)
        if heard and score <= 0.12:
            break
    return best


def synthesize(text: str, out_path: str) -> Optional[str]:
    if not os.path.exists(REF_PATH):
        return None
    lines = split_lines(text)
    if not lines:
        return None
    work = tempfile.mkdtemp(prefix="vox_")
    try:
        ref = upload_ref()
    except Exception as e:
        log("upload ref error:", str(e)[:200])
        return None
    files, report = [], []
    for i, line in enumerate(lines):
        path, score, heard = gen_line(line, ref, work, i)
        if not path or score > MAX_CER:
            log(f"line {i} ไม่ผ่าน (cer={score:.2f}) -> ใช้เสียงสำรอง")
            return None
        files.append(path)
        report.append(f"{score:.2f} | บท: {line} | ได้ยิน: {heard}")
    # ต่อท่อนด้วยช่วงเงียบ 0.2 วินาที
    inputs, filt = [], []
    for i, p in enumerate(files):
        inputs += ["-i", p]
        filt.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=mono,silenceremove=start_periods=1:"
                    f"start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,"
                    f"areverse,apad=pad_dur=0.2[a{i}]")
    filt.append("".join(f"[a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=0:a=1,atempo={TEMPO}[out]")
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filt),
                        "-map", "[out]", "-ar", "44100", "-b:a", "160k", out_path], check=True)
    except Exception as e:
        log("concat error:", e)
        return None
    log("OK", " / ".join(report))
    try:
        import engine
        engine.annotate("notice", "VOX check", "\n".join(report))
    except Exception:
        pass
    return out_path if os.path.getsize(out_path) > 1000 else None
