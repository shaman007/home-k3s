import requests

# ---- CONFIG ----
base_url = "https://shaman007.com"  # or your Synapse backend if behind a reverse proxy
admin_token = ""
user_id = "@a:shaman007.com"

# Account data types to delete
account_data_keys = [
    "m.cross_signing.master",
    "m.cross_signing.self_signing",
    "m.cross_signing.user_signing",
    "m.secret_storage.default_key",
    "m.secret_storage.key",
    "m.megolm_backup.v1"
]

headers = {
    "Authorization": f"Bearer {admin_token}"
}

for key in account_data_keys:
    url = f"{base_url}/_synapse/admin/v1/user/{user_id}/account_data/{key}"
    print(f"Deleting {key}... ", end="")
    response = requests.delete(url, headers=headers)
    if response.status_code == 200:
        print("✅")
    else:
        print(f"❌ {response.status_code} - {response.text}")
