# 룰루레몬 상품 옵션 크롤링 프로그램 요구사항

## 1. 목적
네이버 스마트스토어 재고 관리를 위해 **룰루레몬 캐나다 공식 홈페이지의 상품 옵션 정보를 자동으로 수집하여 엑셀 파일로 생성하는 프로그램**이 필요합니다.

입력된 상품 URL을 기준으로 **색상, 사이즈, 재고 여부, 옵션 가격 정보**를 확인하여 **상품별 엑셀 파일을 자동 생성**하는 기능이 요구됩니다.

---

# 2. 입력 방식

프로그램에 **룰루레몬 상품 URL 목록을 입력**합니다.

예시 URL


https://shop.lululemon.com/en-ca/p/womens-leggings/Align-Pant-2/_/prod2020015?color=72763

https://shop.lululemon.com/en-ca/p/womens-leggings/Align-HighRise-Tight-25-Pockets/_/prod10370246?color=72763

https://shop.lululemon.com/en-ca/p/womens-leggings/lululemon-Align-No-Line-High-Rise-Pant-25/_/prod11900027?color=33190


- 최대 **약 50개의 URL을 한번에 입력하여 크롤링**할 수 있어야 합니다.

---

# 3. 출력 결과

입력된 **URL 1개당 엑셀 파일 1개 생성**

예시


URL 1 → product_1.xlsx
URL 2 → product_2.xlsx
URL 3 → product_3.xlsx


각 엑셀 파일은 **첨부된 샘플 엑셀 양식과 동일한 구조**로 생성되어야 합니다.

---

# 4. 엑셀 파일 컬럼 구성

엑셀에는 다음 컬럼이 포함되어야 합니다.

| 컬럼명 | 설명 |
|------|------|
| 컬러 | 상품 색상 |
| 사이즈 | 상품 사이즈 |
| 옵션가 | 색상별 가격 차이에 따른 옵션 가격 |
| 재고수량 | 재고 여부에 따른 수량 |
| 관리코드 | 옵션 관리 코드 |
| 사용여부 | 옵션 사용 여부 |

---

# 5. 재고 수량 처리 규칙

룰루레몬 사이트에서 **재고 여부를 확인하여 다음 규칙으로 표시합니다.**

| 상태 | 재고수량 |
|------|------|
| 재고 있음 | 5 |
| 재고 없음 | 0 |

---

# 6. 컬러명 처리 규칙

컬러명은 **25자 제한 규칙**이 필요합니다.

- 컬러명이 **25자를 초과할 경우 자동 축약**
- 축약 방식은 **단어 약어 방식 사용**

예시


Heathered Core Ultra Light Grey
→ Heathered CULG


---

# 7. 옵션 가격 계산 규칙

같은 상품이라도 **색상별 가격이 다른 경우 옵션가 자동 계산**

예시


제품 가격 범위
108 CAD ~ 128 CAD


가격 기준


기준 가격 = 최저가


옵션 가격 계산 방식


옵션가 = (색상 가격 - 최저가) × 환율


환율 기준


1 CAD = 1,000 KRW


예시

| 색상 가격 | 옵션가 |
|------|------|
| 108 CAD | 0 |
| 113 CAD | 5,000 |
| 128 CAD | 20,000 |

---

# 8. 크롤링 대상 정보

각 상품 페이지에서 다음 정보를 수집해야 합니다.

- 색상 목록
- 사이즈 목록
- 색상별 가격
- 색상/사이즈별 재고 여부

---

# 9. 처리 흐름

프로그램 동작 흐름


URL 입력
↓
상품 페이지 접속
↓
색상 목록 수집
↓
사이즈 목록 수집
↓
재고 여부 확인
↓
가격 차이 계산
↓
옵션 데이터 생성
↓
상품별 엑셀 파일 생성


---

# 10. 사이즈 정렬 규칙 (추가 요청사항)

남성 제품 URL의 경우 **사이즈 추출 순서가 불규칙하게 출력되는 문제**가 확인되었습니다.

엑셀 파일 생성 시 **사이즈는 아래 순서로 정렬되어 출력되어야 합니다.**


XS
S
M
L
XL
XXL


현재 일부 남성 상품에서 **사이즈가 랜덤 순서로 출력되는 문제가 발생**하고 있으므로  
**엑셀 생성 시 위 사이즈 순서 기준으로 정렬하여 출력하는 기능이 필요합니다.**

---

# 11. 참고 URL


https://shop.lululemon.com/en-ca/p/womens-leggings/Align-Pant-2/_/prod2020015?color=0001

https://shop.lululemon.com/en-ca/p/womens-leggings/Align-Pant-Full-Length-28/_/prod8780304?color=25461

https://shop.lululemon.com/en-ca/p/womens-leggings/Align-Pant-Super-Hi-Rise-28/_/prod9200196?color=0001

https://shop.lululemon.com/en-ca/p/womens-leggings/Align-Pant-Tall/_/prod9410008?color=38344

https://shop.lululemon.com/en-ca/p/women-crops/Align-Crop-21/_/prod8780230?color=0001

https://shop.lululemon.com/en-ca/p/women-crops/Align-Crop-23/_/prod9610002?color=62468

https://shop.lululemon.com/en-ca/p/womens-leggings/Align-HighRise-Crop-23-Pockets/_/prod10370243?color=25461

https://shop.lululemon.com/en-ca/p/womens-leggings/Align-HighRise-Tight-25-Pockets/_/prod10370246?color=28926

https://shop.lululemon.com/en-ca/p/womens-leggings/Align-Pant-Full-Length-28-Pockets/_/prod9230084?color=28926

https://shop.lululemon.com/en-ca/p/womens-leggings/lululemon-Align-No-Line-High-Rise-Pant-25/_/prod11900027?color=31382

https://shop.lululemon.com/en-ca/p/womens-leggings/lululemon-Align-No-Line-High-Rise-Pant-28/_/prod11900023?color=25461

https://shop.lululemon.com/en-ca/p/womens-leggings/Align-No-Line-HR-Twist-Tight-25/_/prod20006792?color=0554