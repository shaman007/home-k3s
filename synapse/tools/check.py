import requests

HOMESERVER = "https://shaman007.com"
USER_ID = "@a:shaman007.com"
ACCESS_TOKEN = ""

url = f"{HOMESERVER}/_matrix/client/v3/devices"
headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

resp = requests.get(url, headers=headers)
print(resp.json())
