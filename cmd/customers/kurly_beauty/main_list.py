import requests


def get_kurly_list(cookie_str="", category_no=167001):
    result = []
    page = 1

    while True:
        url = f"https://api.kurly.com/collection/v2/home/sites/beauty/product-categories/{category_no}/products"
        params = {
            "sort_type": 1,
            "page": page,
            "per_page": 96,
            "filters": "",
        }
        headers = {
            "accept": "application/json, text/plain, */*",
            "origin": "https://www.kurly.com",
            "referer": f"https://www.kurly.com/categories/{category_no}?filters=&page={page}&site=beauty&per_page=96&sorted_type=1",
            "user-agent": "Mozilla/5.0",
        }

        if cookie_str.strip():
            headers["cookie"] = cookie_str.strip()

        res = requests.get(url, params=params, headers=headers, timeout=30)
        res.raise_for_status()

        json_data = res.json()
        data = json_data.get("data", [])

        if not data:
            print(f"page={page} 빈배열 -> 중단")
            break

        rows = []
        for item in data:
            rows.append({
                "no": item.get("no"),
                "name": item.get("name", ""),
            })

        print(rows)
        result.extend(rows)
        page += 1

    return result


if __name__ == "__main__":
    cookie_str = ""
    result = get_kurly_list(cookie_str=cookie_str, category_no=167001)
    print(result)