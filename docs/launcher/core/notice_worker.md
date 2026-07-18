# notice_worker.py

## 핵심 정의

`notice_worker.py`는 긴급 공지 API 호출을 메인 화면과 분리된 스레드에서 실행한다.

공지 조회 중에도 런처 화면이 멈추지 않도록 `QThread`를 사용한다.

---

## 핵심 흐름

```text
NoticeWorker 생성
    ↓
server_url, program_id 저장
    ↓
별도 스레드에서 공지 API 호출
    ↓
조회 결과를 NoticeResult로 구성
    ↓
sig_done 시그널로 메인 화면에 전달
```

---

## NoticeResult

공지 API 호출 결과를 하나의 객체로 전달한다.

| 항목 | 내용 |
|---|---|
| `ok` | API 호출 성공 여부 |
| `message` | 성공 또는 실패 메시지 |
| `notice` | 조회된 공지 정보, 공지가 없으면 `None` |

---

## NoticeWorker

`QThread`를 상속받아 긴급 공지 조회를 백그라운드 스레드에서 처리한다.

```text
입력
├─ server_url
└─ program_id

출력
└─ sig_done(NoticeResult)
```

`run()`에서 다음 함수를 호출한다.

```python
fetch_latest_notice(
    self.server_url,
    self.program_id,
)
```

조회가 끝나면 결과를 메인 화면에 전달한다.

```python
self.sig_done.emit(
    NoticeResult(ok, message, notice)
)
```

---

## 예외 처리

공지 API 호출 중 예상하지 못한 오류가 발생해도 스레드를 그대로 종료하지 않는다.

```text
예외 발생
    ↓
ok=False
    ↓
오류 메시지와 notice=None 구성
    ↓
sig_done으로 메인 화면에 전달
```

메인 화면은 전달받은 결과를 확인한 뒤 공지 조회 실패 로그를 남기고 업데이트 확인을 계속 진행한다.

---

## 핵심 역할

```text
NoticeWorker
    → 긴급 공지 API를 별도 스레드에서 호출

NoticeResult
    → 공지 조회 결과를 묶어서 전달

sig_done
    → 조회 완료 결과를 메인 화면에 전달
```
