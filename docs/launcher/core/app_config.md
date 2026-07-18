# app_config.py

## 핵심 정의

`app_config.py`는 `data/app.json`에서 공식 사이트와 문의/Q&A 주소를 읽어 런처에 전달한다.

---

## 핵심 흐름

```text
data/app.json 경로 생성
    ↓
파일 존재 여부 확인
    ↓
JSON 읽기
    ↓
support 항목 확인
    ↓
site_url, qna_url 검증
    ↓
SupportConfig 객체 반환
```

---

## app.json 형식

```json
{
  "support": {
    "site_url": "https://goodbye772.com",
    "qna_url": "https://goodbye772.com/faq"
  }
}
```

| 항목 | 내용 |
|---|---|
| `site_url` | 공식 사이트 주소 |
| `qna_url` | 문의/Q&A 페이지 주소 |

---

## SupportConfig

검증이 끝난 지원 페이지 주소를 하나의 객체로 관리한다.

```text
SupportConfig
├─ site_url
└─ qna_url
```

`frozen=True`이므로 생성된 이후 값을 변경할 수 없다.

---

## 실패 처리

다음 상황에서는 오류를 발생시키지 않고 `None`을 반환한다.

- `app.json` 파일이 없음
- JSON 형식이 잘못됨
- `support` 항목이 없음
- `site_url` 또는 `qna_url`이 없음
- URL 값이 문자열이 아니거나 빈 값임

런처는 반환값이 `None`이면 지원 센터 영역을 표시하지 않는다.

---

## 핵심 역할

```text
load_support_config()
    → app.json의 지원 페이지 설정 읽기
    → 필수 값 검증
    → 정상일 때 SupportConfig 반환
    → 문제가 있으면 None 반환
```