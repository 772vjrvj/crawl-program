import requests
import json

def test_major_repair_api(pnu, api_key):
    # Spring Boot 로컬 서버 주소 (포트가 다르면 수정하세요)
    url = "https://goodbye772.com/archhub/major-repair"

    headers = {
        "X-API-KEY": api_key
    }

    params = {
        "pnu": pnu
    }

    print(f"요청 URL: {url}?pnu={pnu}")
    print("-" * 50)

    try:
        # GET 요청 전송
        response = requests.get(url, headers=headers, params=params)

        # 상태 코드 출력
        print(f"HTTP 상태 코드: {response.status_code}")

        # 응답 데이터 파싱 및 한글 깨짐 방지(ensure_ascii=False) 포맷팅
        response_data = response.json()
        formatted_json = json.dumps(response_data, indent=4, ensure_ascii=False)

        print("응답 JSON:")
        print(formatted_json)

    except requests.exceptions.RequestException as e:
        print(f"요청 중 오류 발생: {e}")

if __name__ == "__main__":
    # application-local.yaml에 설정한 외부 수집용 마스터 키
    MASTER_API_KEY = "my_secret_master_key_1234!"

    # 테스트 시나리오 1: 정상적인 PNU 조회 (성공 기대)
    print("=== [테스트 1] 정상 PNU 조회 ===")
    test_major_repair_api(pnu="1168010300100130003", api_key=MASTER_API_KEY)
    print("\n" + "="*50 + "\n")

    # 테스트 시나리오 2: 잘못된 PNU 조회 (400 Bad Request 기대)
    print("=== [테스트 2] 잘못된 PNU 조회 ===")
    test_major_repair_api(pnu="INVALID_PNU_123", api_key=MASTER_API_KEY)
    print("\n" + "="*50 + "\n")

    # 테스트 시나리오 3: 잘못된 API 키 (401 Unauthorized 기대)
    print("=== [테스트 3] 인증 실패 ===")
    test_major_repair_api(pnu="1168010100108120002", api_key="WRONG_KEY")