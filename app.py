import requests

PAGE_ID = "110817595401376"
PAGE_ACCESS_TOKEN = "EAAMU12USPiwBQ3xEejlecZBmyhsB2O7qFk2pK8g2D2q6KFt8ZCR8KTUoIDcqOBRZBfDWhrZCN1JSXlELmphelf94ZBb5cMtKUqT5mnrNZCMxLXCKlZBFu3sqSZBd4OB6yzth7jZBuSUHvtYbpzq9xZBJcmGZCCA46E0jqjlWrI17LnwvcZCr7MUVqTZCZCkMGPB6WxPohh5LtROSiZCudttZB42jRdspVf6eOaxHsVo4xG4Ns95VqdBwHAVeRSJQx7BdPrp7"

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
