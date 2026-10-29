"""
ตรวจลิงก์ Shopee ในโพสต์/คลิปล่าสุดของทั้ง 2 เพจ (อ่านอย่างเดียว ไม่แก้ไขอะไรในเพจ)
- ดึงโพสต์ + Reels ล่าสุด, หาลิงก์ในข้อความและคอมเมนต์ของเพจเอง
- เปิดลิงก์แบบมือถือ ตามการ redirect แล้วดูว่าไปจบที่หน้าสินค้า Shopee และยังมีรหัส Affiliate อยู่ไหม
- ดึงสถิติโพสต์ (ถ้า Facebook อนุญาต)
"""
import json
import os
import re
from urllib.parse import parse_qs, unquote, urlparse

import requests

GRAPH = "https://graph.facebook.com/v25.0"
UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Mobile Safari/537.36")
LINK_RE = re.compile(r"https?://[^\s<>\"]+")
N_POSTS = int(os.getenv("N_POSTS", "8"))
N_REELS = int(os.getenv("N_REELS", "4"))

PAGES = [
    {"mode": "ben", "id": os.getenv("PAGE_ID", ""), "token": os.getenv("PAGE_ACCESS_TOKEN", "")},
    {"mode": "smart", "id": os.getenv("PAGE_ID_2", ""), "token": os.getenv("PAGE_ACCESS_TOKEN_2", "")},
]


def annotate(level, title, msg):
    msg = msg.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::{level} title={title}::{msg}", flush=True)


def g(path, token, **params):
    params["access_token"] = token
    try:
        return requests.get(f"{GRAPH}/{path}", params=params, timeout=30).json()
    except Exception as e:
        return {"error": {"message": str(e)}}


def check_link(url):
    """คืน dict ผลการเปิดลิงก์"""
    out = {"ok": False, "status": None, "final": "", "aff": False, "hops": 0, "note": ""}
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "th-TH,th;q=0.9"},
                         allow_redirects=True, timeout=30)
        out["status"] = r.status_code
        out["hops"] = len(r.history)
        out["final"] = r.url
        chain = " ".join([h.headers.get("location", "") for h in r.history] + [r.url, url])
        out["aff"] = ("affiliate_id=" in chain) or ("mmp_pid=an_" in chain) or ("an_redir" in chain and "affiliate_id" in url)
        host = urlparse(r.url).netloc
        body = r.text[:200000] if r.ok else ""
        if "shopee" not in host:
            out["note"] = f"ไปจบที่ {host} ไม่ใช่ Shopee"
        elif r.status_code >= 400:
            out["note"] = f"HTTP {r.status_code}"
        elif re.search(r"สินค้านี้ไม่มีอยู่|product.{0,20}not.{0,10}(exist|found)|item_not_found", body, re.I):
            out["note"] = "หน้าสินค้าแจ้งว่าไม่มีสินค้านี้"
        else:
            out["ok"] = True
        # ดึงลิงก์ปลายทางจริงจาก origin_link (ถ้ามี) เพื่อแสดง
        q = parse_qs(urlparse(url).query)
        if "origin_link" in q:
            out["origin"] = unquote(q["origin_link"][0])
    except Exception as e:
        out["note"] = f"เปิดไม่ได้: {str(e)[:120]}"
    return out


def mask(url):
    return re.sub(r"(affiliate_id=)\d+", r"\1***", url)


def post_insights(pid, token):
    res = g(f"{pid}/insights", token, metric="post_impressions_unique,post_clicks,post_clicks_by_type")
    if "error" in res:
        return f"insights: {res['error'].get('message', '')[:100]}"
    vals = {}
    for m in res.get("data", []):
        v = (m.get("values") or [{}])[0].get("value")
        vals[m.get("name")] = v
    return json.dumps(vals, ensure_ascii=False)


def main():
    for page in PAGES:
        if not page["id"] or not page["token"]:
            continue
        mode, token = page["mode"], page["token"]
        lines, bad = [], 0
        items = []
        posts = g(f"{page['id']}/posts", token, fields="id,message,created_time", limit=N_POSTS)
        if "error" in posts:
            annotate("error", f"Linkcheck {mode}", f"posts: {posts['error'].get('message')}")
        items += [("โพสต์", p) for p in posts.get("data", [])]
        reels = g(f"{page['id']}/video_reels", token, fields="id,description,created_time", limit=N_REELS)
        if "error" in reels:
            lines.append(f"(อ่าน Reels ไม่ได้: {reels['error'].get('message', '')[:120]})")
        items += [("คลิป", {"id": r["id"], "message": r.get("description", ""), "created_time": r.get("created_time", "")})
                  for r in reels.get("data", [])]

        for kind, it in items:
            pid = it["id"]
            text = it.get("message") or ""
            links = LINK_RE.findall(text)
            com = g(f"{pid}/comments", token, fields="message,from", limit=10)
            com_links = []
            for c in com.get("data", []):
                if (c.get("from") or {}).get("id") == page["id"]:
                    com_links += LINK_RE.findall(c.get("message", ""))
            where = []
            if links:
                where.append("ในแคปชัน")
            if com_links:
                where.append("ในคอมเมนต์")
            all_links = list(dict.fromkeys(links + com_links))
            when = it.get("created_time", "")[:16].replace("T", " ")
            head = f"[{kind} {when} UTC] {(text.splitlines() or [''])[0][:50]}"
            if not all_links:
                lines.append(f"❌ {head}\n   ไม่มีลิงก์เลย")
                bad += 1
                continue
            for u in all_links[:2]:
                r = check_link(u)
                mark = "✅" if r["ok"] and r["aff"] else "❌"
                if mark == "❌":
                    bad += 1
                lines.append(
                    f"{mark} {head}\n   ลิงก์{'/'.join(where)}: {mask(u)[:120]}\n"
                    f"   -> {r['status']} {mask(r['final'])[:110]} | redirect {r['hops']} ครั้ง | affiliate={'มี' if r['aff'] else 'ไม่มี'}"
                    + (f" | {r['note']}" if r["note"] else "")
                )
            if kind == "โพสต์":
                lines.append("   สถิติ: " + post_insights(pid, token))
        annotate("notice" if bad == 0 else "warning", f"Linkcheck {mode}",
                 f"ตรวจ {len(items)} รายการ มีปัญหา {bad}\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
