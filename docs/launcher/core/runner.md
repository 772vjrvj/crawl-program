# runner.py

## 핵심 정의

`runner.py`는 런처가 설치된 실제 프로그램 EXE를 새로운 프로세스로 실행하는 역할을 담당한다.

런처가 종료된 이후에도 실행한 프로그램이 계속 동작할 수 있도록 `subprocess.Popen()`을 사용한다.

---

## 핵심 흐름

```text
EXE 경로 전달
    ↓
EXE 파일 존재 여부 확인
    ↓
작업 폴더 결정
    ↓
새로운 프로세스로 EXE 실행
    ↓
즉시 반환 또는 종료까지 대기
    ↓
실행 결과 반환
```

---

## run_exe()

```python
run_exe(
    exe_path,
    workdir=None,
    wait=False,
)
```

| 매개변수 | 내용 |
|---|---|
| `exe_path` | 실행할 EXE 파일 전체 경로 |
| `workdir` | 프로그램 실행 기준 폴더 |
| `wait` | 프로그램 종료까지 기다릴지 여부 |

---

## 작업 폴더 결정

`workdir`이 있으면 해당 경로를 사용한다.

```text
workdir 전달
    → 전달받은 폴더 사용
```

`workdir`이 없으면 EXE 파일이 들어 있는 폴더를 사용한다.

```text
workdir=None
    → exe_path.parent 사용
```

예:

```text
exe_path
E:\GB7Launcher\versions\v1_0_2\CrawlProgram.exe

기본 작업 폴더
E:\GB7Launcher\versions\v1_0_2
```

실행 프로그램이 같은 폴더의 설정 파일, DLL, 이미지 등을 찾을 수 있도록 EXE가 있는 폴더를 기본 작업 폴더로 사용한다.

---

## subprocess.Popen()

```python
process = subprocess.Popen(
    [str(exe_path)],
    cwd=cwd,
    close_fds=True,
)
```

`Popen()`은 새로운 프로세스를 시작한다.

| 설정 | 내용 |
|---|---|
| `[str(exe_path)]` | 실행할 프로그램 |
| `cwd=cwd` | 프로그램 작업 폴더 |
| `close_fds=True` | 런처의 불필요한 파일 핸들을 새 프로세스에 넘기지 않음 |

`Popen()`은 기본적으로 프로그램 종료를 기다리지 않는다.

```text
런처가 EXE 실행
    ↓
새 프로그램 프로세스 생성
    ↓
런처는 바로 다음 작업 진행
```

따라서 런처가 종료되어도 실제 프로그램은 독립적으로 계속 실행된다.

---

## wait 옵션

### wait=False

일반적인 런처 실행 방식이다.

```text
프로그램 실행
    ↓
즉시 성공 결과 반환
    ↓
런처 종료 가능
    ↓
실제 프로그램은 계속 실행
```

반환값:

```python
(True, "ok", None)
```

### wait=True

실행한 프로그램이 종료될 때까지 기다린다.

```text
프로그램 실행
    ↓
프로그램 종료까지 대기
    ↓
종료 코드 반환
```

반환값:

```python
(True, "ok(wait)", exit_code)
```

일반적으로 종료 코드 `0`은 정상 종료를 의미하지만, 정확한 의미는 실행 프로그램 정책에 따라 달라질 수 있다.

런처 운영에서는 보통 `wait=False`를 사용하고, `wait=True`는 테스트나 디버깅에 사용한다.

---

## 반환값

```python
Tuple[bool, str, Optional[int]]
```

| 위치 | 내용 |
|---|---|
| 첫 번째 | 실행 성공 여부 |
| 두 번째 | 결과 메시지 |
| 세 번째 | 종료 코드 또는 `None` |

### 실행 성공, 대기하지 않음

```python
(True, "ok", None)
```

### 실행 성공, 종료까지 대기

```python
(True, "ok(wait)", 0)
```

### 실행 실패

```python
(False, "run failed: 오류 내용", None)
```

### EXE 파일 없음

```python
(False, "exe not found: 경로", None)
```

---

## 실패 처리

다음 상황에서는 실패 결과를 반환한다.

- EXE 파일이 존재하지 않음
- 실행 권한이 없음
- EXE 파일이 손상됨
- 작업 폴더에 접근할 수 없음
- 운영체제에서 프로세스를 생성하지 못함

예외를 바깥으로 그대로 발생시키지 않고 다음 형식으로 반환한다.

```python
(
    False,
    "run failed: 오류 내용",
    None,
)
```

---

## 핵심 역할

```text
run_exe()
    → EXE 존재 확인
    → 작업 폴더 결정
    → 새 프로세스로 프로그램 실행
    → 필요하면 종료 코드 대기
    → 성공 또는 실패 결과 반환
```

런처에서는 일반적으로 다음 방식으로 사용한다.

```python
ok, message, exit_code = run_exe(
    exe_path,
    wait=False,
)
```
