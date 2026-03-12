import requests,os

KEY=os.environ["OPENAI_API_KEY"]

def tts(text):

    r=requests.post(
    "https://api.openai.com/v1/audio/speech",
    headers={"Authorization":f"Bearer {KEY}"},
    json={
    "model":"gpt-4o-mini-tts",
    "voice":"alloy",
    "input":text
    })

    open("voice.mp3","wb").write(r.content)
