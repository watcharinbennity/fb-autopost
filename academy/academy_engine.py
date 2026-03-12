import os,json,requests

from academy_topics import CURRICULUM
from diagram_generator import *
from video_builder import *

OPENAI=os.environ["OPENAI_API_KEY"]
PAGE=os.environ["PAGE_ID"]
TOKEN=os.environ["PAGE_ACCESS_TOKEN"]

STATE="academy/state.json"


def load():

    if os.path.exists(STATE):

        return json.load(open(STATE))

    return {"initialized":False,"episode":0}


def save(data):

    json.dump(data,open(STATE,"w"))


def tts(text):

    r=requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization":f"Bearer {OPENAI}"},
        json={
            "model":"gpt-4o-mini-tts",
            "voice":"alloy",
            "input":text
        }
    )

    open("voice.mp3","wb").write(r.content)


def upload(video,caption):

    url=f"https://graph.facebook.com/v25.0/{PAGE}/videos"

    r=requests.post(
        url,
        files={"source":open(video,"rb")},
        data={
            "description":caption,
            "access_token":TOKEN
        }
    )

    print(r.text)


def run_intro():

    draw_intro("img.png")

    build_video("img.png","v.mp4")

    tts("สวัสดีครับ ผมช่างเบน เราจะเรียนไฟฟ้าตั้งแต่พื้นฐาน จนถึงระดับวิศวกร")

    add_audio("v.mp4","voice.mp3","final.mp4")

    upload("final.mp4","⚡ เปิดตัว BEN Home & Electrical Academy")


def run_episode(ep):

    title,type=CURRICULUM[ep]

    if type=="series":
        draw_series("img.png",title)

    elif type=="meter":
        draw_meter("img.png",title)

    elif type=="current":
        draw_current("img.png",title)

    else:
        draw_intro("img.png")

    caption=f"EP{ep+1} {title}"

    requests.post(
        f"https://graph.facebook.com/v25.0/{PAGE}/feed",
        data={
            "message":caption,
            "access_token":TOKEN
        }
    )


state=load()

if not state["initialized"]:

    run_intro()

    state["initialized"]=True
    save(state)

else:

    ep=state["episode"]

    run_episode(ep)

    state["episode"]=ep+1

    save(state)
