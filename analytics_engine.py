import json

def best_products():

    try:

        with open("posted_log.json") as f:

            logs=json.load(f)

    except:

        return []

    best=[]

    for l in logs:

        if int(l["sold"])>100:

            best.append(l)

    return best
