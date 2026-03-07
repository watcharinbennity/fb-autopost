def filter_products(rows,state):

    products=[]

    for r in rows:

        try:

            rating=float(r.get("item_rating") or 0)
            sold=int(float(r.get("item_sold") or 0))
            price=float(r.get("sale_price") or r.get("price") or 0)

        except:
            continue

        if rating < 4.5:
            continue

        if sold < 100:
            continue

        if price < 20 or price > 300:
            continue

        link=r.get("product_link")

        if link in state["posted"]:
            continue

        image=r.get("image_link")

        if not image:
            continue

        products.append({
            "name":r.get("title"),
            "link":link,
            "image":image,
            "price":price,
            "rating":rating,
            "sold":sold
        })

    return products
