import requests


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
API_KEY = "SERVER31234"
USER_ID = "test_user_01"


def test_search():
    url = f"{BASE_URL}/bizno/search"
    headers = {
        "X-API-KEY": API_KEY
    }
    params = {
        "userId": USER_ID,
        "companyName": "정음속기녹취사무소",
        "ownerName": "김수용"
    }

    response = requests.get(url, headers=headers, params=params, timeout=20)

    print("=== SEARCH ===")
    print("REQUEST URL :", response.request.url)
    print("STATUS CODE :", response.status_code)
    print("RESPONSE JSON:", response.json())

    return response.json()


def test_detail(article: str):
    url = f"{BASE_URL}/bizno/detail"
    headers = {
        "X-API-KEY": API_KEY
    }
    params = {
        "userId": USER_ID,
        "article": article
    }

    response = requests.get(url, headers=headers, params=params, timeout=20)

    print("=== DETAIL ===")
    print("REQUEST URL :", response.request.url)
    print("STATUS CODE :", response.status_code)
    print("RESPONSE TEXT:")
    print(response.text)

    try:
        print("RESPONSE JSON:")
        print(response.json())
    except Exception:
        print("JSON 파싱 실패")


if __name__ == "__main__":
    search_result = test_search()

    if search_result.get("success") and search_result.get("article"):
        test_detail(search_result["article"])
    else:
        print("search 실패 또는 article 없음")