"""
ตัวจัดตารางโพสต์ (ใช้แค่ไลบรารีมาตรฐาน รันได้ก่อนติดตั้งอะไร)

GitHub Actions cron มักช้าหลายชั่วโมงและบางรอบหาย จึงให้ workflow ปลุกทุก 15 นาที
แล้วสคริปต์นี้ตัดสินจากเวลาไทยว่ามีรอบไหน "ถึงเวลาและยังไม่ได้ทำ" วันนี้

  python scheduler.py check posts            -> due=true/false, slot=HHMM (เขียนลง GITHUB_OUTPUT)
  python scheduler.py mark posts 0900 success -> บันทึกผล
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

STATE_FILE = "schedule_state.json"
BKK = timezone(timedelta(hours=7))

SLOTS = {
    "posts": ["0900", "1200", "1830", "2100"],
    "reels": ["1930"],
}
QUIET_START = "2300"   # หลังเวลานี้ไม่โพสต์ (รอบที่ค้างจะถูกข้าม)
QUIET_END = "0800"
MAX_ATTEMPTS = 2       # รอบที่ล้มเหลว ลองซ้ำได้อีก 1 ครั้ง (เช่น Shopee ตอบ 429)


def now_bkk() -> datetime:
    fake = os.getenv("FAKE_NOW")  # สำหรับทดสอบ: "2026-10-06 09:05"
    if fake:
        return datetime.strptime(fake, "%Y-%m-%d %H:%M").replace(tzinfo=BKK)
    return datetime.now(BKK)


def load() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save(data: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def today_state(data: dict, kind: str, today: str) -> dict:
    st = data.get(kind) or {}
    if st.get("date") != today:
        st = {"date": today, "slots": {}}
    data[kind] = st
    return st


def due_slot(kind: str, now: datetime, data: dict):
    hhmm = now.strftime("%H%M")
    if hhmm >= QUIET_START or hhmm < QUIET_END:
        return None
    st = today_state(data, kind, now.strftime("%Y-%m-%d"))
    passed = [s for s in SLOTS[kind] if s <= hhmm]
    if not passed:
        return None
    latest = passed[-1]  # ถ้าค้างหลายรอบ ทำแค่รอบล่าสุด (ไม่โพสต์รัว ๆ ย้อนหลัง)
    rec = st["slots"].get(latest, {})
    if rec.get("result") == "success" or rec.get("attempts", 0) >= MAX_ATTEMPTS:
        return None
    return latest


def output(**kw) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    lines = [f"{k}={v}" for k, v in kw.items()]
    print(" ".join(lines), flush=True)
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def main() -> None:
    cmd, kind = sys.argv[1], sys.argv[2]
    now = now_bkk()
    data = load()

    if cmd == "check":
        slot = due_slot(kind, now, data)
        output(due="true" if slot else "false", slot=slot or "", now=now.strftime("%H:%M"))
        return

    if cmd == "mark":
        slot, outcome = sys.argv[3], sys.argv[4]
        st = today_state(data, kind, now.strftime("%Y-%m-%d"))
        rec = st["slots"].setdefault(slot, {"attempts": 0})
        rec["attempts"] = rec.get("attempts", 0) + 1
        rec["result"] = "success" if outcome == "success" else "failure"
        rec["at"] = now.strftime("%H:%M")
        save(data)
        print(f"marked {kind} {slot}: {rec}", flush=True)
        return

    raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
