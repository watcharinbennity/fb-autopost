"""
หาลิงก์สินค้า Shopee (มีรหัส Affiliate) ให้คลิปสอนไฟฟ้าที่ท่านลงเองในเพจ BEN
- อ่าน Reels ล่าสุดของเพจ เลือกเฉพาะคลิปที่ไม่มีลิงก์ Shopee ในแคปชัน (คลิปที่ลงเอง)
- ให้ Claude อ่านแคปชันแล้วบอกว่าสินค้าอะไรเกี่ยวกับเนื้อหาคลิป (คำค้น)
- ค้นใน Shopee feed เลือกสินค้าที่ตรงที่สุด รีวิวดี ขายดี
- อ่านอย่างเดียว ไม่โพสต์ ไม่คอมเมนต์ ไม่แก้อะไรในเพจ ผลเก็บไว้ที่ productlink_result.json
"""
import json
import os
import re

import requests

import engine

N_REELS = int(os.getenv("N_REELS", "10"))
ONLY_TEXT = os.getenv("CLIP_TEXT", "").strip()
BRAND = [b.strip().lower() for b in os.getenv("BRAND", "").split(",") if b.strip()]  # เช่น "schneider,ชไนเดอร์"  # ถ้าใส่ข้อความเอง จะหาลิงก์ให้ข้อความนี้แทนการอ่านจากเพจ


# ไม่ใช่อุปกรณ์ไฟฟ้า (กันคำพ้อง เช่น "wind breaker" = เสื้อแจ็กเก็ต)
NOT_TOOLS = ["เสื้อ", "แจ็คเก็ต", "แจ๊คเก็ต", "jacket", "windbreaker", "wind breaker", "กางเกง", "รองเท้า", "หมวก"]


def clips_without_link():
    page = engine.PAGES[0]  # BEN
    res = requests.get(f"{engine.GRAPH}/{page['id']}/video_reels",
                       params={"fields": "id,description,created_time", "limit": N_REELS,
                               "access_token": page["token"]}, timeout=30).json()
    out = []
    for r in res.get("data", []):
        d = r.get("description") or ""
        if "shopee" in d.lower():
            continue  # คลิปของบอท (มีลิงก์อยู่แล้ว)
        out.append({"id": r["id"], "time": r.get("created_time", "")[:16], "text": d})
    return out


def keywords_for(text):
    prompt = f"""คลิปสอนไฟฟ้าในเพจ BEN Home & Electrical มีแคปชันนี้:
{text}

ระบุสินค้าบน Shopee 1 ประเภทที่เกี่ยวข้องกับเนื้อหาคลิปมากที่สุด และคนดูคลิปนี้น่าจะอยากซื้อ
(เช่น คลิปตู้ไฟ -> ตู้คอนซูมเมอร์ยูนิต, คลิปปลั๊ก -> ปลั๊กพ่วง มอก., คลิปไขควงวัดไฟ -> ไขควงวัดไฟ)
ตอบ JSON อย่างเดียว:
{{"product": "ชื่อประเภทสินค้าภาษาไทย", "must": ["คำที่ชื่อสินค้าต้องมีอย่างน้อย 1 คำ ทั้งไทยและอังกฤษ"], "avoid": ["คำที่ถ้ามีในชื่อแปลว่าไม่ใช่สินค้าที่ต้องการ"]}}"""
    raw = engine.ai_write("คุณเป็นช่างไฟฟ้าที่รู้จักสินค้าบน Shopee ตอบ JSON เท่านั้น", prompt, temperature=0.2, max_tokens=500)
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except Exception:
        data = {}
    data["must"] = [str(x).lower() for x in data.get("must", []) if str(x).strip()]
    data["avoid"] = [str(x).lower() for x in data.get("avoid", []) if str(x).strip()]
    return data


def main():
    if ONLY_TEXT:
        clips = [{"id": f"manual{i}", "time": "", "text": t.strip()} for i, t in enumerate(ONLY_TEXT.split("||")) if t.strip()]
    else:
        clips = clips_without_link()
    for c in clips:
        c["want"] = keywords_for(c["text"])
        c["cands"] = []
    clips = [c for c in clips if c["want"].get("must")]

    for row in engine.iter_csv_rows(engine.SHOPEE_CSV_URL):
        title = engine.norm_text(row.get("title"))
        low = title.lower()
        rating = engine.to_float(row.get("item_rating"))
        sold = engine.to_float(row.get("item_sold"))
        if rating < float(os.getenv("LINK_MIN_RATING", "4.5")) or sold < float(os.getenv("LINK_MIN_SOLD", "20")):
            continue
        for c in clips:
            w = c["want"]
            if not engine.has_kw(low, w["must"]) or engine.has_kw(low, w["avoid"] + NOT_TOOLS):
                continue
            if BRAND and not any(b in low for b in BRAND):
                continue
            score = sold * rating
            c["cands"].append((score, row))
            c["cands"].sort(key=lambda x: -x[0])
            del c["cands"][5:]

    result = []
    for c in clips:
        picks = []
        for score, row in c["cands"][:3]:
            link = engine.build_shopee_affiliate_link(row, "ben").replace("sub_id=fbbot-", "sub_id=fbclip-")
            picks.append({"title": engine.norm_text(row.get("title"))[:120],
                          "price": engine.to_float(row.get("sale_price")),
                          "rating": engine.to_float(row.get("item_rating")),
                          "sold": int(engine.to_float(row.get("item_sold"))),
                          "link": link})
        result.append({"clip": c["text"][:1500], "time": c["time"], "id": c["id"],
                       "product": c["want"].get("product"), "must": c["want"].get("must"), "picks": picks})
        engine.annotate("notice" if picks else "warning", "Clip link",
                        f"{c['text'][:60]} -> {c['want'].get('product')} : {len(picks)} ตัวเลือก")
    with open("productlink_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
