import requests

PAGE_ID = "110817595401376"
PAGE_ACCESS_TOKEN = "https://www.facebook.com/profile.php?id=100069823276627"

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
