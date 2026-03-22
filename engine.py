import os
import random
from utils import iter_csv_rows, load_json_file, save_json_file, log, image_key_from_url
from filters import build_ben_product, build_smart_product
from ai_caption import generate_caption, generate_comment_text
from facebook_post import post_product

CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()
MAX_ROWS = 200000
TOP_KEEP = 1200
TOP_POOL = 20


def score_product(product, page_mode):
    sold = float(product["sold"])
    rating = float(product["rating"])
    commission = float(product.get("commission", 0.0))
    price = float(product.get("price", 0.0))
    group = product.get("group", "")

    sold_score = sold * 2.2
    rating_score = rating * 14.0
    commission_score = commission * 1.1

    hot_bonus = 50 if sold >= 1000 else 0
    social_bonus = 20 if sold >= 300 else 0

    if page_mode == "ben":
        if group == "electrical":
            if 100 <= price <= 2000:
                price_bonus = 30
            elif 2000 < price <= 3000:
                price_bonus = 10
            else:
                price_bonus = 0
        elif group == "tools":
            if 300 <= price <= 5000:
                price_bonus = 30
            elif 5000 < price <= 15000:
                price_bonus = 12
            else:
                price_bonus = 0
        else:
            price_bonus = 0
    else:
        # smart home
        if group == "camera":
            price_bonus = 35 if 300 <= price <= 3000 else 10
        elif group == "robot_vacuum":
            price_bonus = 35 if 1500 <= price <= 12000 else 10
        elif group in ["router", "smart_plug", "smart_bulb", "smart_switch"]:
            price_bonus = 30 if 150 <= price <= 4000 else 8
        else:
            price_bonus = 0

    return sold_score + rating_score + commission_score + hot_bonus + social_bonus + price_bonus


def choose_product(csv_url, posted_path, page_mode):
    posted_data = load_json_file(posted_path, default={"ids": [], "image_keys": []})
    posted_ids = set(posted_data.get("ids", []))
    posted_images = set(posted_data.get("image_keys", []))

    candidates = []
    rows_seen = 0
    build_none = 0
    dup_id = 0
    dup_image = 0
    accepted = 0

    builder = build_ben_product if page_mode == "ben" else build_smart_product

    for row in iter_csv_rows(csv_url, max_rows=MAX_ROWS):
        rows_seen += 1

        product = builder(row)
        if not product:
            build_none += 1
            continue

        if product["id"] in posted_ids:
            dup_id += 1
            continue

        img_key = image_key_from_url(product["image"])
        if img_key in posted_images:
            dup_image += 1
            continue

        product["image_key"] = img_key
        product["score"] = score_product(product, page_mode)
        candidates.append(product)
        accepted += 1

        if len(candidates) > TOP_KEEP:
            candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)[:TOP_KEEP]

    log(f"[{page_mode}] rows_seen={rows_seen}")
    log(f"[{page_mode}] build_none={build_none}")
    log(f"[{page_mode}] dup_id={dup_id}")
    log(f"[{page_mode}] dup_image={dup_image}")
    log(f"[{page_mode}] accepted={accepted}")
    log(f"[{page_mode}] candidates={len(candidates)}")

    if not candidates:
        return None, posted_data

    elite = sorted(candidates, key=lambda x: x["score"], reverse=True)[:TOP_POOL]
    chosen = random.choice(elite)

    log(
        f"[{page_mode}] CHOSEN => {chosen['title']} "
        f"| sold={chosen['sold']} "
        f"| rating={chosen['rating']} "
        f"| price={chosen['price']:.2f} "
        f"| commission={chosen['commission']:.2f} "
        f"| group={chosen['group']} "
        f"| score={chosen['score']:.2f}"
    )

    return chosen, posted_data


def run_single_page(page_mode, page_id, access_token, posted_path):
    if not page_id or not access_token:
        log(f"[{page_mode}] missing PAGE_ID or ACCESS_TOKEN")
        return

    product, posted_data = choose_product(CSV_URL, posted_path, page_mode)
    if not product:
        log(f"[{page_mode}] NO PRODUCT FOUND")
        return

    caption = generate_caption(product, page_mode=page_mode)
    comment_text = generate_comment_text(product, page_mode=page_mode)

    post_id = post_product(
        page_id=page_id,
        access_token=access_token,
        product=product,
        caption=caption,
        comment_text=comment_text,
    )

    if post_id:
        posted_data["ids"].append(product["id"])
        posted_data["image_keys"].append(product["image_key"])
        posted_data["ids"] = posted_data["ids"][-5000:]
        posted_data["image_keys"] = posted_data["image_keys"][-5000:]
        save_json_file(posted_path, posted_data)
        log(f"[{page_mode}] POSTED SUCCESS => {product['title']}")
    else:
        log(f"[{page_mode}] POST FAILED")


def run_all_pages():
    log("BEN + SMARTHOME ULTRA ENGINE START")

    page_id_ben = os.getenv("PAGE_ID", "").strip()
    token_ben = os.getenv("PAGE_ACCESS_TOKEN", "").strip()

    page_id_smart = os.getenv("PAGE_ID_2", "").strip()
    token_smart = os.getenv("PAGE_ACCESS_TOKEN_2", "").strip()

    run_single_page(
        page_mode="ben",
        page_id=page_id_ben,
        access_token=token_ben,
        posted_path="posted_ben.json",
    )

    run_single_page(
        page_mode="smart",
        page_id=page_id_smart,
        access_token=token_smart,
        posted_path="posted_smart.json",
        )
