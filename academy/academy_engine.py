import json
import os
import requests

from academy_topics import CURRICULUM
from diagram_generator import *
from video_builder import image_to_video


PAGE_ID=os.environ["PAGE_ID"]
PAGE_TOKEN=os.environ["PAGE_ACCESS_TOKEN"]

STATE_FILE="academy/state.json"



def load_state():

    with open(STATE_FILE,"r") as f:
        return json.load(f)



def save_state(s):

    with open(STATE_FILE,"w") as f:
        json.dump(s,f)



def generate_video(topic):

    img="lesson.png"

    if topic["type"]=="series":
        create_series_circuit(img)

    elif topic["type"]=="parallel":
        create_parallel_circuit(img)

    else:
        create_series_circuit(img)

    video="lesson.mp4"

    image_to_video(img,video)

    return video



def upload(video,title):

    url=f"https://graph.facebook.com/v25.0/{PAGE_ID}/videos"

    files={"source":open(video,"rb")}

    data={
    "description":title,
    "access_token":PAGE_TOKEN
    }

    r=requests.post(url,files=files,data=data)

    print(r.text)



def main():

    state=load_state()

    m=state["module_index"]
    t=state["topic_index"]

    module=CURRICULUM[m]

    topic=module["topics"][t]

    print("POST:",topic["title"])

    video=generate_video(topic)

    upload(video,topic["title"])


    t+=1

    if t>=len(module["topics"]):

        t=0
        m+=1

        if m>=len(CURRICULUM):
            m=0


    state["module_index"]=m
    state["topic_index"]=t

    save_state(state)



if __name__=="__main__":
    main()
