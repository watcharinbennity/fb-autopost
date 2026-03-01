import requests

PAGE_ID = "110817595401376"
PAGE_ACCESS_TOKEN = "EAAMU12USPiwBQyeUZBcacFDuo7Nw5fVSff0uP2L84HZCLjTuFsETOR8itLiPGOA0EgyKTLRM5kggt2CExjs4T1P2Mw5EeXZA1xDyZAbOc4OaOiEGPiB4h5fu7P0E9uLAYkVq8h7uXINAIbnP8PVL23rn7SUcsgUNgk8nXZC6pfe1F3GHstQwz202XIhwnX3AJW3Oi1PChaKKyDZCTWKi2emlzuNK7mzyf07l9erYASica34ZAZBbewvCZCdIZD"

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
