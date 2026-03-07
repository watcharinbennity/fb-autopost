KEYWORDS=[
"ไฟ","led","โคม","หลอดไฟ",
"ปลั๊ก","สวิตช์","สายไฟ",
"เครื่องมือ","ไขควง","สว่าน",
"diy","solar","โซล่า"
]

def filter_products(rows,state):

    products=[]

    posted=set(state.get("posted",[]))

    for r in rows:

        title=(r.get("title") or "").lower()

        if not any(k in title for k in KEYWORDS):
            continue

        link=r.get("product_link")

        image=r.get("image_link")

        if not link or not image:
            continue

        if link in posted:
            continue

        rating=float(r.get("item_rating") or 0)

        sold=int(float(r.get("item_sold") or 0))

        if rating<4:
            continue

        if sold<10:
            continue

        products.append({
            "name":r.get("title"),
            "link":link,
            "image":image,
            "price":r.get("price"),
            "rating":rating,
            "sold":sold
        })

    return products
