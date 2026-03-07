import random

VIRAL_POSTS=[

{
"topic":"ไฟโซล่าดีไหม",
"image":"https://i.imgur.com/3g7nmJC.jpg"
},

{
"topic":"ปลั๊กไฟแบบไหนปลอดภัย",
"image":"https://i.imgur.com/QX8QK0L.jpg"
},

{
"topic":"เครื่องมือช่างที่ควรมีติดบ้าน",
"image":"https://i.imgur.com/OnqT5pE.jpg"
},

{
"topic":"5 อุปกรณ์ไฟฟ้าที่ควรมีติดบ้าน",
"image":"https://i.imgur.com/9XqvF2C.jpg"
}

]

def viral_post():

    post=random.choice(VIRAL_POSTS)

    return post["topic"],post["image"]
