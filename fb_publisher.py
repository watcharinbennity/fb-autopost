import requests

def upload_photo(page_id,token,url):

    endpoint=f"https://graph.facebook.com/v25.0/{page_id}/photos"

    payload={
        "url":url,
        "published":"false",
        "access_token":token
    }

    r=requests.post(endpoint,data=payload)

    return r.json()["id"]
