from PIL import Image,ImageDraw,ImageFont
import os

W=1080
H=1920

def base(title):

    img=Image.new("RGB",(W,H),(7,18,33))
    draw=ImageDraw.Draw(img)

    draw.rounded_rectangle((40,40,1040,170),30,fill=(15,35,55))
    draw.text((70,80),"BEN Home & Electrical",(255,255,255))

    draw.text((70,220),title,(255,220,60))

    draw.rounded_rectangle((80,380,1000,1500),40,outline="white",width=6)

    return img,draw


def draw_intro(path):

    img,draw=base("เปิดตัว BEN Home & Electrical Academy")

    draw.text((140,520),"สวัสดีครับ ผมช่างเบน",(255,255,255))

    draw.text((140,640),"เราจะเรียนไฟฟ้าตั้งแต่",(255,220,60))
    draw.text((140,720),"พื้นฐาน จนถึงระดับวิศวกร",(255,220,60))

    draw.text((140,900),"เข้าใจง่าย",(255,255,255))
    draw.text((140,980),"ใช้ได้จริง",(255,255,255))
    draw.text((140,1060),"ค่อย ๆ ไต่ระดับไปด้วยกัน",(255,255,255))

    img.save(path)


def draw_current(path,title):

    img,draw=base(title)

    y=1000

    draw.line((200,y,900,y),fill="yellow",width=10)

    for x in [350,500,650,800]:

        draw.polygon(
            [(x,y-30),(x+60,y),(x,y+30)],
            fill="red"
        )

    draw.text((200,860),"ทิศทางการไหลของกระแส",(255,220,60))

    img.save(path)


def draw_series(path,title):

    img,draw=base(title)

    y=1000

    draw.line((200,y,400,y),fill="yellow",width=10)

    draw.rectangle((400,930,480,1070),outline="white",width=5)

    draw.line((480,y,650,y),fill="yellow",width=10)

    draw.rectangle((650,930,730,1070),outline="white",width=5)

    draw.line((730,y,900,y),fill="yellow",width=10)

    img.save(path)


def draw_meter(path,title):

    img,draw=base(title)

    draw.rectangle((350,750,750,1200),outline="white",width=5)

    draw.rectangle((420,820,680,980),outline="green",width=4)

    draw.text((460,860),"220V",(0,255,0))

    draw.text((450,1050),"Multimeter",(255,255,255))

    img.save(path)
