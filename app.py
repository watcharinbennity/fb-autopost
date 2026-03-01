import os
import requests
from datetime import datetime

PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

if not PAGE_ID or not PAGE_ACCESS_TOKEN:
    raise Exception("❌ Missing PAGE_ID or PAGE_ACCESS_TOKEN")

# ข้อความที่จะโพสต์
message = f"""
🔥 โปรโมชันประจำวัน
โพสต์อัตโนมัติด้วยระบบ 🤖
เวลาโพสต์: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

payload = {
    "message": message,
    "access_token": PAGE_ACCESS_TOKEN
}

response = requests.post(url, data=payload)

print(response.json())
