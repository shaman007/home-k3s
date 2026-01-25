import requests

# CONFIGURE THESE
HOMESERVER = "https://shaman007.com"
ACCESS_TOKEN = ""

# Dummy keys (not secure, just for testing)
# Dummy keys (just placeholders)
device_keys = {
    "algorithms": [
        "m.olm.v1.curve25519-aes-sha2",
        "m.megolm.v1.aes-sha2"
    ],
    "device_id": "FAKEDEVICE",
    "user_id": "@andrey:shaman007.com",
    "keys": {
        "curve25519:FAKEDEVICE": "",
        "ed25519:FAKEDEVICE": "tsdfrestasasded25fsd9kg22ey"
    }
}

dehydrated_device = {
    "device_id": "FAKEDEVICE",  # 🔥 This must be top-level
    "device_data": {
        "display_name": "Dehydrated Test Device",
        "algorithm": "m.megolm.v1.aes-sha2"  # 🔥 required!
    },
    "device_keys": device_keys
}

url = f"{HOMESERVER}/_matrix/client/unstable/org.matrix.msc3814.v1/dehydrated_device?access_token={ACCESS_TOKEN}"

response = requests.put(url, json=dehydrated_device)

print(f"Status code: {response.status_code}")
try:
    print("Response:", response.json())
except Exception:
    print("Non-JSON response:", response.text)
