import requests

PAGE_ID = "PUT_PAGE_ID_HERE"
PAGE_ACCESS_TOKEN = "PUT_PAGE_ACCESS_TOKEN_HERE"

def post_to_facebook(message):
    url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/feed"
    payload = {
        "message": message,
        "access_token": PAGE_ACCESS_TOKEN
    }
    res = requests.post(url, data=payload)
    print(res.json())

if __name__ == "__main__":
    post_to_facebook("ทดสอบโพสต์จากสคริปต์ 🚀")
