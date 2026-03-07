KEYWORDS=[
"ไฟ","led","โคม","หลอดไฟ",
"ปลั๊ก","ปลั๊กไฟ","สวิตช์",
"สายไฟ","เบรกเกอร์",
"เครื่องมือ","ไขควง","สว่าน",
"คีม","ประแจ","DIY",
"โซล่า","solar","แบตเตอรี่"
]


def score_product(title,rating,sold):

    score=0

    t=title.lower()

    for k in KEYWORDS:

        if k in t:

            score+=10

    score+=rating*20
    score+=sold*0.05

    return score
