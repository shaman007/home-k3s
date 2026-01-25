import requests

HOMESERVER = "https://shaman007.com"
ACCESS_TOKEN = ""

# This should match the ID of your dehydrated device
DEHYDRATED_DEVICE_ID = "FAKEDEVICE"

# This device_id will become the "rehydrated" active device
NEW_DEVICE_ID = "REHYDRATED123"

# Optional metadata
display_name = "Rehydrated via script"

url = f"{HOMESERVER}/_matrix/client/unstable/org.matrix.msc3814.v1/rehydrate_device?access_token={ACCESS_TOKEN}"

payload = {
    "device_id": NEW_DEVICE_ID,
    "initial_device_display_name": display_name,
    "dehydrated_device_id": DEHYDRATED_DEVICE_ID
}

resp = requests.post(url, json=payload)

print(f"Status: {resp.status_code}")
try:
    print("Response:", resp.json())
except Exception:
    print("Raw response:", resp.text)
