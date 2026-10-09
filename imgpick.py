"""
เลือกรูปสินค้าที่ "เห็นสินค้าชัด" ไว้เป็นรูปแรก
รูปที่ดี = สินค้าบนพื้นหลังเรียบ (ขอบรูปสีเดียวกัน) และมีตัวหนังสือ/กราฟิกน้อย
รูปแบนเนอร์ที่อัดตัวหนังสือเต็ม จะมีขอบลายและเส้นขอบ (edge) หนาแน่น -> คะแนนต่ำ
"""
import io
from typing import List, Optional

import requests
from PIL import Image, ImageFilter, ImageStat


def image_score(img: Image.Image) -> float:
    im = img.convert("RGB")
    im.thumbnail((256, 256))
    w, h = im.size
    if w < 40 or h < 40:
        return -1.0
    b = max(3, int(min(w, h) * 0.06))
    strips = [im.crop((0, 0, w, b)), im.crop((0, h - b, w, h)), im.crop((0, 0, b, h)), im.crop((w - b, 0, w, h))]
    # ขอบเรียบ: ส่วนเบี่ยงเบนสีของขอบรูปต่ำ = พื้นหลังสะอาด
    border_std = sum(sum(ImageStat.Stat(s).stddev) / 3 for s in strips) / 4
    border_clean = max(0.0, 1.0 - border_std / 60.0)
    # ความหนาแน่นของเส้นขอบทั้งภาพ: ตัวหนังสือ/กราฟิกเยอะ = สูง
    edges = im.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_density = ImageStat.Stat(edges).mean[0] / 255.0
    busy = min(1.0, edge_density / 0.18)
    return round(border_clean * 1.0 - busy * 0.8, 4)


def best_first(images: List[Image.Image]) -> List[int]:
    """คืนลำดับ index: รูปที่คะแนนสูงสุดขึ้นก่อน ที่เหลือคงลำดับเดิม"""
    if len(images) < 2:
        return list(range(len(images)))
    scores = [image_score(im) for im in images]
    top = max(range(len(images)), key=lambda i: scores[i])
    return [top] + [i for i in range(len(images)) if i != top]


def order_urls(urls: List[str], check: int = 6, timeout: int = 20) -> List[str]:
    """ดาวน์โหลดรูปแรก ๆ มาให้คะแนน แล้วย้ายรูปที่ชัดที่สุดขึ้นเป็นรูปแรก (ผิดพลาด = คืนลำดับเดิม)"""
    if len(urls) < 2:
        return urls
    loaded: List[Optional[Image.Image]] = []
    head = urls[:check]
    for u in head:
        try:
            r = requests.get(u, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            loaded.append(Image.open(io.BytesIO(r.content)))
        except Exception:
            loaded.append(None)
    ok = [i for i, im in enumerate(loaded) if im is not None]
    if len(ok) < 2:
        return urls
    order = best_first([loaded[i] for i in ok])
    best = head[ok[order[0]]]
    return [best] + [u for u in urls if u != best]
