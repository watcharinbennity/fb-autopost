import json
import os
import requests

from academy_topics import CURRICULUM
from diagram_generator import create_circuit
from video_builder import build_video

PAGE_ID=os.environ["PAGE_ID"]
TOKEN=os.environ["PAGE_ACCESS_TOKEN"]

STATE_FILE="academy/state.json"


def load_state():

    with open(STATE_FILE,"r") as f:
        return json.load(f)


def save_state(s):

    with open(STATE_FILE,"w") as f:
        json.dump(s,f)


def create_video():

    img="lesson.png"
    video="lesson.mp4"

    create_circuit(img)
    build_video(img,video)

    return video


def upload(video,caption):

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/videos"

    files={"source":open(video,"rb")}

    data={
    "description":caption,
    "access_token":TOKEN
    }

    r=requests.post(url,files=files,data=data)

    print(r.text)


def main():

    state=load_state()

    ep=state["episode"]

    topic=CURRICULUM[ep]

    title=f"EP{ep+1} {topic['title']}"

    print("POST:",title)

    video=create_video()

    upload(video,title)

    state["episode"]=ep+1

    save_state(state)


if __name__=="__main__":
    main()
