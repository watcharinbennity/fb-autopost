import random

def score(product):

    score=0

    score+=product["rating"]*40
    score+=product["sold"]*0.6

    if product["price_num"] < 300:
        score+=20

    score+=random.random()*5

    return score


def choose_product(products):

    ranked=sorted(products,key=score,reverse=True)

    return ranked[0]
