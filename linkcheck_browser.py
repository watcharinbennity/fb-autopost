"""เปิดลิงก์ Shopee จริงด้วยเบราว์เซอร์มือถือ (รัน JavaScript) แล้วดูว่าไปจบที่หน้าสินค้าไหม + ถ่ายภาพหน้าจอ"""
import json
import sys

from playwright.sync_api import sync_playwright

res = json.load(open("linkcheck_result.json", encoding="utf-8"))
targets = []
for mode in ("ben", "smart"):
    for e in res.get(mode, []):
        for l in e.get("links", []):
            if l.get("origin"):
                targets.append((mode, e["text"].splitlines()[0][:40] if e["text"] else "", l["origin"]))
                break
        if len([t for t in targets if t[0] == mode]) >= 2:
            break

out = []
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(**p.devices["Pixel 7"], locale="th-TH")
    for i, (mode, head, origin) in enumerate(targets):
        # ใช้ลิงก์รูปแบบเดียวกับในโพสต์ (ไม่ใส่ affiliate_id จริง เพื่อไม่ให้นับคลิกปลอม)
        url = "https://s.shopee.co.th/an_redir?origin_link=" + __import__("urllib.parse").parse.quote(origin, safe="")
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(8000)
            final = page.url
            title = page.title()
            shot = f"shot_{mode}_{i}.png"
            page.screenshot(path=shot)
            txt = page.inner_text("body")[:300].replace("\n", " ")
            out.append({"mode": mode, "post": head, "start": url, "final": final, "title": title, "text": txt, "shot": shot})
        except Exception as e:
            out.append({"mode": mode, "post": head, "start": url, "error": str(e)[:200]})
        page.close()
    b.close()
json.dump(out, open("linkcheck_browser.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
sys.exit(0)
