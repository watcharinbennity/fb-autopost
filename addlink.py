"""เพิ่มลิงก์สินค้า Shopee ให้คลิปที่ลงเองในเพจ BEN: ต่อท้ายแคปชัน + คอมเมนต์ลิงก์ (ถ้ายังไม่มี)"""
import json
import os
import re
import sys

import requests

GRAPH = "https://graph.facebook.com/v25.0"
TOKEN = os.environ["PAGE_ACCESS_TOKEN"]
PAGE_ID = os.environ["PAGE_ID"]
JOBS = json.loads(os.environ["JOBS"])  # [{"video_id": "...", "link": "...", "label": "..."}]


def annotate(level, title, msg):
    print(f"::{level} title={title}::" + msg.replace("%", "%25").replace("\n", "%0A"), flush=True)


fail = 0
for job in JOBS:
    vid, link, label = job["video_id"], job["link"], job.get("label", "")
    if not re.fullmatch(r"\d+", vid) or not re.match(r"https://s\.shopee\.co\.th/an_redir\?.*affiliate_id=\d+", link):
        annotate("error", f"Addlink {vid}", "video_id หรือลิงก์ไม่ถูกรูปแบบ")
        fail += 1
        continue
    info = requests.get(f"{GRAPH}/{vid}", params={"fields": "description,from", "access_token": TOKEN}, timeout=30).json()
    if "error" in info or (info.get("from") or {}).get("id") != PAGE_ID:
        annotate("error", f"Addlink {vid}", f"อ่านคลิปไม่ได้หรือไม่ใช่คลิปของเพจ: {info.get('error', {}).get('message', '')}")
        fail += 1
        continue
    desc = info.get("description") or ""
    done = []
    # เปลี่ยนสินค้า: เอาลิงก์เดิมที่บอทเคยใส่ (sub_id=fbclip-) ออกก่อน ทั้งในแคปชันและคอมเมนต์
    old_block = re.compile(r"\n*🛒[^\n]*\n👉 https://s\.shopee\.co\.th/an_redir\?[^\s]*sub_id=fbclip-[^\s]*")
    if link not in desc and old_block.search(desc):
        desc = old_block.sub("", desc)
        done.append("ลบลิงก์เดิมในแคปชัน")
    for c in requests.get(f"{GRAPH}/{vid}/comments", params={"fields": "id,message,from", "limit": 50,
                                                             "access_token": TOKEN}, timeout=30).json().get("data", []):
        msg = c.get("message") or ""
        if (c.get("from") or {}).get("id") == PAGE_ID and "sub_id=fbclip-" in msg and link not in msg:
            r = requests.delete(f"{GRAPH}/{c['id']}", params={"access_token": TOKEN}, timeout=30).json()
            done.append("ลบคอมเมนต์ลิงก์เดิม: " + ("OK" if r.get("success") else str(r)[:100]))
    if link not in desc:
        new_desc = desc.rstrip() + f"\n\n🛒 {label}\n👉 {link}"
        r = requests.post(f"{GRAPH}/{vid}", data={"description": new_desc, "access_token": TOKEN}, timeout=30).json()
        done.append("แคปชัน: " + ("OK" if r.get("success") else json.dumps(r, ensure_ascii=False)[:200]))
        if not r.get("success"):
            fail += 1
    else:
        done.append("แคปชัน: มีลิงก์แล้ว")
    coms = requests.get(f"{GRAPH}/{vid}/comments", params={"fields": "message,from", "limit": 50, "access_token": TOKEN},
                        timeout=30).json().get("data", [])
    if any(link in (c.get("message") or "") and (c.get("from") or {}).get("id") == PAGE_ID for c in coms):
        done.append("คอมเมนต์: มีแล้ว")
    else:
        r = requests.post(f"{GRAPH}/{vid}/comments",
                          data={"message": f"🛒 {label}\n👉 {link}", "access_token": TOKEN}, timeout=30).json()
        done.append("คอมเมนต์: " + ("OK" if r.get("id") else json.dumps(r, ensure_ascii=False)[:200]))
        if not r.get("id"):
            fail += 1
    annotate("notice", f"Addlink {vid}", " | ".join(done))
sys.exit(1 if fail else 0)
