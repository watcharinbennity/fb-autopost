import os
import json
import io
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta

PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL")

if not PAGE_ID or not PAGE_ACCESS_TOKEN or not SHOPEE_CSV_URL:
    raise Exception("❌ Missing PAGE_ID / PAGE_ACCESS_TOKEN / SHOPEE_CSV_URL")

STATE_FILE = "state.json"

TH_MONTHS = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
]

# ---------- helper functions ----------
def find_col(df, keywords):
    for col in df.columns:
        for k in keywords:
            if k.lower() in col.lower():
                return col
    return None

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"posted_itemids": []}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def thai_date_str():
    th = timezone(timedelta(hours=7))
    now = datetime.now(th)
    day = now.day
    month = TH_MONTHS[now.month - 1]
    year = now.year + 543
    return f"{day} {month} {year}"

# ---------- download CSV ----------
print("⬇️ Downloading Shopee CSV...")
r = requests.get(SHOPEE_CSV_URL, timeout=120)
r.raise_for_status()
df = pd.read_csv(io.BytesIO(r.content))
print(f"✅ CSV loaded: {len(df)} rows")

# ---------- detect columns ----------
col_itemid = find_col(df, ["itemid", "item_id"])
col_name = find_col(df, ["product_name", "item_name", "name", "title"])
col_link = find_col(df, ["affiliate_link", "product_link", "link", "url"])
col_rating = find_col(df, ["rating"])
col_sold = find_col(df, ["sold", "historical_sold"])
col_price = find_col(df, ["price"])
col_discount = find_col(df, ["discount"])

if not col_link:
    raise Exception("❌ ไม่พบคอลัมน์ลิงก์สินค้าใน CSV")

# ---------- load state ----------
state = load_state()
posted_ids = set(map(str, state.get("posted_itemids", [])))

# ---------- prepare dataframe ----------
work = df.copy()

if col_itemid:
    work["_itemid"] = work[col_itemid].astype(str)
else:
    work["_itemid"] = work[col_link].astype(str)

work = work[~work["_itemid"].isin(posted_ids)]

if work.empty:
    print("♻️ สินค้าหมด รีเซ็ต state")
    state["posted_itemids"] = []
    work = df.copy()
    if col_itemid:
        work["_itemid"] = work[col_itemid].astype(str)
    else:
        work["_itemid"] = work[col_link].astype(str)

# ---------- scoring ----------
score = pd.Series([0.0] * len(work))

if col_rating:
    score += pd.to_numeric(work[col_rating], errors="coerce").fillna(0) * 10

if col_sold:
    score += pd.to_numeric(work[col_sold], errors="coerce").fillna(0) * 0.02

if col_discount:
    score += pd.to_numeric(work[col_discount], errors="coerce").fillna(0) * 2

work["_score"] = score

pick = work.sort_values("_score", ascending=False).head(1).iloc[0]

itemid = str(pick["_itemid"])
name = str(pick[col_name]) if col_name else "สินค้าแนะนำ"
link = str(pick[col_link])

# ---------- build message ----------
rating_txt = f"⭐ เรตติ้ง: {pick[col_rating]}" if col_rating else ""
sold_txt = f"🛒 ขายแล้ว: {pick[col_sold]}" if col_sold else ""
price_txt = f"💰 ราคา: {pick[col_price]}" if col_price else ""
disc_txt = f"🏷️ ส่วนลด: {pick[col_discount]}" if col_discount else ""

thai_date = thai_date_str()

message_lines = [
    "🔥 สินค้าแนะนำวันนี้ (คัดให้อัตโนมัติ)",
    f"✅ {name}",
    rating_txt,
    sold_txt,
    price_txt,
    disc_txt,
    "",
    f"👉 กดดู/สั่งซื้อ: {link}",
    f"📅 อัปเดต: {thai_date}"
]

message = "\n".join([x for x in message_lines if x])

# ---------- post to Facebook ----------
print("📤 Posting to Facebook...")
url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
payload = {
    "message": message,
    "link": link,
    "access_token": PAGE_ACCESS_TOKEN
}

resp = requests.post(url, data=payload, timeout=60)
print("STATUS:", resp.status_code)
print("RESPONSE:", resp.text)

result = resp.json()
if "id" not in result:
    raise Exception(f"❌ Facebook error: {result}")

# ---------- update state ----------
state.setdefault("posted_itemids", [])
state["posted_itemids"].append(itemid)
state["posted_itemids"] = state["posted_itemids"][-500:]
save_state(state)

print("✅ Posted successfully:", result["id"])
