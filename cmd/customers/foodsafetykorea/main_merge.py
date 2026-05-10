import json
import os

def update_foodsafety_data():
    # 파일 경로 설정
    main_file = 'foodsafety_bsn_detail.json'
    rawdata_dir = 'rawdata'
    raw_files = [
        'detail_1023_1312.json',
        'detail_1313_1605.json',
        'detail_1606_1902.json',
        'detail_1902_2200.json',
        'detail_2201_2499.json'
    ]

    # 1. 메인 데이터 로드
    try:
        with open(main_file, 'r', encoding='utf-8') as f:
            main_data = json.load(f)
    except FileNotFoundError:
        print(f"오류: {main_file} 파일을 찾을 수 없습니다.")
        return
    except json.JSONDecodeError:
        print(f"오류: {main_file} 파일의 형식이 올바르지 않습니다.")
        return

    # 2. rawdata 폴더 내 5개 파일의 데이터를 하나의 딕셔너리로 병합 (Key: 번호)
    raw_lookup = {}
    for filename in raw_files:
        filepath = os.path.join(rawdata_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    for item in data:
                        if "번호" in item:
                            # "번호"를 키로 하여 객체 전체를 저장
                            raw_lookup[item["번호"]] = item
                except Exception as e:
                    print(f"파일 읽기 오류 ({filename}): {e}")
        else:
            print(f"경고: {filepath} 파일이 존재하지 않습니다.")

    # 3. 메인 데이터 업데이트 (번호가 일치하는 항목 교체)
    updated_count = 0
    for i in range(len(main_data)):
        key = main_data[i].get("번호")
        if key in raw_lookup:
            main_data[i] = raw_lookup[key]
            updated_count += 1

    # 4. 변경된 데이터를 다시 foodsafety_bsn_detail.json에 저장
    with open(main_file, 'w', encoding='utf-8') as f:
        json.dump(main_data, f, ensure_ascii=False, indent=2)

    # 5. "인허가 정보"가 없는 데이터의 번호 추출 및 출력
    missing_info_keys = []
    for item in main_data:
        # "인허가 정보" 키가 없거나 값이 비어있는 경우
        if "인허가 정보" not in item or not item["인허가 정보"]:
            missing_info_keys.append(item.get("번호"))

    print(f"--- 작업 완료 ---")
    print(f"업데이트된 항목 수: {updated_count}개")
    if missing_info_keys:
        print(f"'인허가 정보'가 없는 데이터 번호: {missing_info_keys}")
    else:
        print("'인허가 정보'가 누락된 데이터가 없습니다.")

if __name__ == "__main__":
    update_foodsafety_data()