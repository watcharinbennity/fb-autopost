"""
รันระบบ Reels:
  python reels_main.py preview  -> สร้างคลิปตัวอย่างเพจละ 1 คลิป (ไม่โพสต์) เก็บใน reels_out/
  python reels_main.py post     -> สร้างคลิปและโพสต์เป็น Reels เพจละ 1 คลิป (DRY_RUN=true = ไม่โพสต์)
"""
import json
import os
import sys
import time
from typing import Dict, Optional

import requests

import engine
import reels

OUT_DIR = "reels_out"
RUPLOAD = "https://rupload.facebook.com/video-upload/v25.0"


def reels_history(posted: Dict) -> Dict:
    hist = {}
    for mode in ("ben", "smart"):
        h = posted.setdefault(f"reels_{mode}", {})
        for k in ("items", "images", "titles"):
            h.setdefault(k, [])
        hist[mode] = h
    return hist


def mark_reel_posted(mode: str, product: Dict) -> None:
    posted = engine.load_posted()
    h = reels_history(posted)[mode]
    for key, val in (("items", product["itemid"]), ("images", product["image_key"]), ("titles", product["title"][:100])):
        if val and val not in h[key]:
            h[key].append(val)
    engine.save_posted(posted)


def graph_post(path: str, data: Dict) -> Dict:
    res = requests.post(f"{engine.GRAPH}/{path}", data=data, timeout=60)
    return engine.safe_json(res)


def publish_reel(page: Dict, video_path: str, caption: str) -> Optional[str]:
    token = page["token"]
    start = graph_post(f"{page['id']}/video_reels", {"upload_phase": "start", "access_token": token})
    err = engine.graph_error(start)
    if err or "video_id" not in start:
        print("❌ REEL START ERROR:", err or start, flush=True)
        engine.annotate("error", f"Reel {page['mode']}", f"start: {err or start}")
        return None
    video_id = start["video_id"]

    size = os.path.getsize(video_path)
    with open(video_path, "rb") as f:
        res = requests.post(
            f"{RUPLOAD}/{video_id}",
            headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)},
            data=f,
            timeout=300,
        )
    up = engine.safe_json(res)
    if engine.graph_error(up) or not up.get("success"):
        print("❌ REEL UPLOAD ERROR:", engine.graph_error(up) or up, flush=True)
        engine.annotate("error", f"Reel {page['mode']}", f"upload: {engine.graph_error(up) or up}")
        return None

    fin = graph_post(
        f"{page['id']}/video_reels",
        {
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": caption,
            "access_token": token,
        },
    )
    err = engine.graph_error(fin)
    if err or not fin.get("success"):
        print("❌ REEL FINISH ERROR:", err or fin, flush=True)
        engine.annotate("error", f"Reel {page['mode']}", f"finish: {err or fin}")
        return None

    # รอ Facebook ประมวลผลวิดีโอ (ไม่เกิน ~3 นาที) ก่อนคอมเมนต์ลิงก์
    status = "unknown"
    for _ in range(18):
        time.sleep(10)
        try:
            st = requests.get(
                f"{engine.GRAPH}/{video_id}",
                params={"fields": "status", "access_token": token},
                timeout=30,
            ).json()
            status = (st.get("status") or {}).get("video_status", "unknown")
        except Exception:
            continue
        if status in ("ready", "published", "error"):
            break
    print(f"REEL STATUS ({page['mode']}): {status}", flush=True)
    if status == "error":
        engine.annotate("error", f"Reel {page['mode']}", "Facebook ประมวลผลวิดีโอไม่ผ่าน")
        return None
    engine.annotate("notice", f"Reel {page['mode']}", f"published video_id={video_id} status={status}")
    return video_id


def main(action: str) -> None:
    dry = engine.DRY_RUN or action == "preview"
    pages = [p for p in engine.PAGES if p["id"] and p["token"]]
    if action == "post":
        pages = [p for p in pages if engine.check_page_token(p)]
    if not pages:
        print("❌ no pages configured", flush=True)
        sys.exit(1)

    posted = engine.load_posted()
    products = engine.choose_products([p["mode"] for p in pages], history=reels_history(posted))

    results, manifest = {}, []
    for page in pages:
        mode = page["mode"]
        product = products.get(mode)
        if not product:
            results[mode] = "no_product"
            continue
        try:
            reel = reels.make_reel(product, mode, OUT_DIR)
        except Exception as e:
            print(f"❌ REEL BUILD ERROR ({mode}):", e, flush=True)
            engine.annotate("error", f"Reel {mode}", f"build: {str(e)[:300]}")
            results[mode] = "build_error"
            continue

        caption = (reel["script"]["caption"] or product["title"]) + f"\n\n👉 กดดูรายละเอียดและราคาล่าสุดตรงนี้\n{product['link']}"
        engine.annotate(
            "notice",
            f"Reel script {mode}",
            f"{product['title'][:70]} | {reel['seconds']:.0f}s voice={'yes' if reel['voice'] else 'no'} "
            f"script={reel['script']['source']} aff_id={'yes' if engine.aff_ok(product['link']) else 'NO'}\n"
            f"จอ: {' / '.join(reel['script']['slides'])}\nพากย์: {reel['script']['voiceover']}\n---\n{caption}",
        )
        manifest.append({"mode": mode, "file": os.path.basename(reel["path"]), "title": product["title"],
                         "slides": reel["script"]["slides"], "voiceover": reel["script"]["voiceover"],
                         "caption": caption, "seconds": reel["seconds"], "voice": reel["voice"]})

        if dry:
            results[mode] = "preview"
            continue
        vid = publish_reel(page, reel["path"], caption)
        if vid:
            mark_reel_posted(mode, product)
            engine.comment_link(vid, page["token"], product["link"])
            results[mode] = "posted"
        else:
            results[mode] = "post_error"

    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    engine.annotate("notice", "Reels summary", " | ".join(f"{m}: {r}" for m, r in results.items()))
    print("REELS SUMMARY:", results, flush=True)
    if any(r not in ("posted", "preview") for r in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "preview")
