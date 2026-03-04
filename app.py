import os
import csv
import json
import time
import requests
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

PAGE_ID = os.getenv("PAGE_ID")
ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")

API_VERSION = "v25.0"
STATE_FILE = "state.json"

def die(msg: str):
    raise SystemExit(f"ERROR: {msg}")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"index": 0}
    return {"index": 0}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)

def fetch_csv_rows(csv_url: str):
    try:
        req = Request(csv_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=30) as r:
            content = r.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError) as e:
        die(f"Cannot fetch CSV: {e}")

    reader = csv.DictReader(content.splitlines())
    rows = []
    for row in reader:
        name = (row.get("name") or "").strip()
        image = (row.get("image") or "").strip()
        url = (row.get("url") or "").strip()

        if not name or not image or not url:
            continue

        rows.append({"name": name, "image": image, "url": url})

    if not rows:
        die("CSV has no usable rows. Need columns: name,image,url and non-empty values.")
    return rows

def looks_like_image_url(u: str) -> bool:
    u_low = u.lower()
    return u_low.startswith("http://") or u_low.startswith("https://")

def validate_image_reachable(image_url: str):
    # เช็คแบบ HEAD ก่อน ถ้าโดนบล็อกค่อย GET แบบเบา ๆ
    try:
        h = requests.head(image_url, timeout=20, allow_redirects=True)
        ct = (h.headers.get("content-type") or "").lower()
        if h.status_code >= 400:
            raise Exception(f"HTTP {h.status_code}")
        if "image/" in ct:
            return True
    except Exception:
        pass

    try:
        g = requests.get(image_url, timeout=20, stream=True, allow_redirects=True)
        ct = (g.headers.get("content-type") or "").lower()
        if g.status_code >= 400:
            raise Exception(f"HTTP {g.status_code}")
        if "image/" in ct:
            return True
    except Exception as e:
        die(f"Image URL not reachable/invalid: {image_url} ({e})")

    # ถ้าไม่เจอ content-type เป็น image ก็ให้ถือว่าเสี่ยง
    die(f"Image URL does not look like a direct image (content-type not image/*): {image_url}")

def post_photo_to_page(page_id: str, access_token: str, image_url: str, caption: str):
    endpoint = f"https://graph.facebook.com/{API_VERSION}/{page_id}/photos"

    payload = {
        "url": image_url,
        "caption": caption,
        "access_token": access_token
    }

    # retry กัน transient
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = requests.post(endpoint, data=payload, timeout=60)
            data = resp.json()
            if resp.status_code >= 400 or "error" in data:
                last_err = data
                time.sleep(2 * attempt)
                continue
            return data
        except Exception as e:
            last_err = {"exception": str(e)}
            time.sleep(2 * attempt)

    die(f"Graph API post failed: {json.dumps(last_err, ensure_ascii=False)}")

def main():
    if not PAGE_ID:
        die("Missing env: PAGE_ID")
    if not ACCESS_TOKEN:
        die("Missing env: PAGE_ACCESS_TOKEN")
    if not CSV_URL:
        die("Missing env: SHOPEE_CSV_URL")

    rows = fetch_csv_rows(CSV_URL)

    state = load_state()
    idx = int(state.get("index", 0))

    if idx >= len(rows):
        idx = 0

    item = rows[idx]
    name = item["name"]
    image_url = item["image"]
    product_url = item["url"]

    if not looks_like_image_url(image_url):
        die(f"Invalid image URL format: {image_url}")

    # เช็คว่าเป็นรูปจริง เข้าถึงได้
    validate_image_reachable(image_url)

    caption = (
        f"🧰 {name}\n\n"
        f"🛒 สั่งซื้อได้ที่:\n{product_url}\n\n"
        f"#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า"
    )

    result = post_photo_to_page(PAGE_ID, ACCESS_TOKEN, image_url, caption)

    print("POST_OK:", json.dumps(result, ensure_ascii=False))

    # อัปเดต state ให้โพสต์ถัดไปเป็นรายการถัดไป
    state["index"] = idx + 1
    save_state(state)

if __name__ == "__main__":
    main()
