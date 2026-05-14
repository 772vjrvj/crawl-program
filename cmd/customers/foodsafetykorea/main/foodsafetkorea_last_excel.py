import pandas as pd
import json

# 1. JSON 파일 읽기
with open('foodsafety_bsn_detail.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

rows = []

# 2. 데이터 추출 및 펼치기
for item in data:
    products = item.get("제조품목 정보", [])

    if not products:  # 제조품목 정보가 없는 경우
        row = {
            "번호": item.get("번호"),
            "업체명": item.get("업체명"),
            "품목제조번호": "",
            "식품의 유형": "",
            "제품명": "",
            "일자": "",
            "지역": item.get("지역"),
            "업종": item.get("업종"),
            "대표자": item.get("대표자"),
            "소재지": item.get("소재지"),
            "제품상세키": ""
        }
        rows.append(row)
    else:  # 제조품목 정보가 있는 경우 (N개만큼 반복)
        for product in products:
            row = {
                "번호": item.get("번호"),
                "업체명": item.get("업체명"),
                "품목제조번호": product.get("품목제조번호"),
                "식품의 유형": product.get("식품의 유형"),
                "제품명": product.get("제품명"),
                "일자": product.get("일자"),
                "지역": item.get("지역"),
                "업종": item.get("업종"),
                "대표자": item.get("대표자"),
                "소재지": item.get("소재지"),
                "제품상세키": product.get("제품상세키")
            }
            rows.append(row)

# 3. 엑셀 파일로 저장
df = pd.DataFrame(rows)
df.to_excel("food_safety_result.xlsx", index=False)

print("엑셀 파일 생성이 완료되었습니다.")