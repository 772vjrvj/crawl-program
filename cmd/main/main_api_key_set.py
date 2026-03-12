import requests
import json


# http://404notfoundshop.shop
# server3-api-key-2026
# SERVER3

# https://www.rapportcompany.co.kr
# server4-api-key-2026
# SERVER4

# https://doublestock.co.kr
# server2-api-key-2026
# SERVER2


BASE_URL = "http://404notfoundshop.shop"
ADMIN_UPDATE_KEY = "gb7-admin-update-key-1234"

url = f"{BASE_URL}/internal/api-key-info/save"

headers = {
    "X-ADMIN-KEY": ADMIN_UPDATE_KEY,
    "Content-Type": "application/json"
}

payload = {
    "serverId": "SERVER3",
    "serverUrl": "http://404notfoundshop.shop",
    "serverApiKey": "server3-api-key-2026",
    "useYn": "Y",
    "createDt": "2026-03-12 10:30:00"
}

try:
    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=20
    )

    print("=== API KEY INFO SAVE TEST ===")
    print("REQUEST URL :", response.request.url)
    print("STATUS CODE :", response.status_code)
    print("REQUEST HEADERS :", headers)
    print("REQUEST BODY :")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("RESPONSE TEXT :")
    print(response.text)

    try:
        print("RESPONSE JSON :")
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    except Exception as e:
        print("JSON 파싱 실패 :", str(e))

except Exception as e:
    print("요청 실패 :", str(e))