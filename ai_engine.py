import random

def price_score(price):

    if price <= 99:
        return 25

    if price <= 299:
        return 20

    if price <= 699:
        return 12

    return 5


def ai_score(product):

    score=0

    score+=product["rating"]*40
    score+=product["sold"]*0.5
    score+=price_score(product["price_num"])

    score+=random.random()*5

    return score


def choose_product(products):

    ranked=sorted(products,key=ai_score,reverse=True)

    top=ranked[:40]

    return random.choice(top)
