import os,json,requests

from curriculum import LESSONS
from scene_builder import *
from animation_engine import *
from voice_engine import *
from video_builder import *

PAGE=os.environ["PAGE_ID"]
TOKEN=os.environ["PAGE_ACCESS_TOKEN"]

STATE="academy/state.json"


def load():

    if os.path.exists(STATE):
        return json.load(open(STATE))

    return {"intro_done":False,"episode":0}


def save(s):

    json.dump(s,open(STATE,"w"))


def upload(video,caption):

    url=f"https://graph.facebook.com/v25.0/{PAGE}/videos"

    r=requests.post(
        url,
        files={"source":open(video,"rb")},
        data={
        "description":caption,
        "access_token":TOKEN
        })

    print(r.text)


state=load()

if not state["intro_done"]:

    img,_=canvas("เปิดตัว BEN Home & Electrical Academy")

    img.save("img.png")

    animate("img.png","intro.mp4")

    tts("สวัสดีครับ ผมช่างเบน เราจะเรียนไฟฟ้าตั้งแต่พื้นฐาน ไปจนถึงระดับวิศวกร")

    merge("intro.mp4","voice.mp3","final.mp4")

    upload("final.mp4","⚡ เปิดตัว BEN Home & Electrical Academy")

    state["intro_done"]=True

    save(state)

else:

    ep=state["episode"]

    title,type=LESSONS[ep]

    if type=="series":
        img=series(title)

    elif type=="parallel":
        img=parallel(title)

    elif type=="flow":
        img=flow(title)

    else:
        img,_=canvas(title)

    img.save("img.png")

    animate("img.png","video.mp4")

    tts(title)

    merge("video.mp4","voice.mp3","final.mp4")

    upload("final.mp4",f"EP{ep+1} {title}")

    state["episode"]=ep+1

    save(state)
