# 수정 사항

날짜 : 2026-03-11
고객 : 특별한꿀벌6962
거래금액 : 30,000
버전 : 2.0.1

---

## 수정 내용


■ 1 이름 번호 제거

현재 0_Pierre-Auguste Renoir 
변경 Pierre-Auguste Renoir → 폴더명 앞의 페이지 번호 제거 이미지 파일명 규칙 변경

namePath = f"{imagePath}/{pageInfo}_{nameInfo}"
namePath = f"{imagePath}/{nameInfo}"


현재 0_001_0001_Albert Bierstadt_California Redwoods_13292 
변경 Albert Bierstadt_California Redwoods_13292 → 파일명 앞의 0_001_0001_ 제거
filename = f"{pageInfo}_{artistNum}_{pieceNumInfo}_{nameInfo}_{pieceInfo}_{idInfo}"
filename = f"{nameInfo}_{pieceInfo}_{idInfo}"



■ 2 변수 추가

cannot access local variable 'artistName' where it is not associated with a value 오류로 인한 종료
변수 추가




■ 3 타입 수정

andas\core\internals\blocks.py:521: FutureWarning: Setting an item of incompatible dtype is deprecated and will raise an error in a future version of pandas. Value '' has dtype incompatible with float64, please explicitly cast to a compatible dtype first.

if "이미지 저장여부" in df_excel.columns:
df_excel["이미지 저장여부"] = df_excel["이미지 저장여부"].astype("object")
df_excel["이미지 저장여부"] = df_excel["이미지 저장여부"].where(pd.notna(df_excel["이미지 저장여부"]), "")


---

## 수정 사유


---

## 영향 범위


---

## 제한 사항


## 빌드
