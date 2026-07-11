서버 로그 추적 구조 정리
1. 목적

프로그램이 메인 서버에서 작업하다가 봇 감지 또는 요청 실패가 발생하면 API 서버로 작업을 넘겨 계속 처리한다.
이때 어느 프로그램 실행에서, 어느 서버 구간을 거쳐, 어떤 개별 요청이, 몇 번째 재시도에서, 어느 서버에서 처리되었는지를 추적할 수 있도록 서버별 로그 구조를 통일한다.

또한 각 서버는 자신의 DB에 로그를 남기고, 메인 서버는 주기적으로 API 서버들의 로그를 수집하여 통합 로그 DB를 유지한다.

2. 서버 구성

구성 서버는 다음과 같다.

main 서버

api 서버1

api 서버2

api 서버3

api 서버4

프로그램 동작 기본 흐름은 다음과 같다.

프로그램은 main 서버에서 로그인한다.

최초 작업도 main 서버에서 수행한다.

main 서버 작업 중 봇 감지, 차단, 요청 실패 등으로 정상 응답을 받지 못하면 다음 API 서버로 전환한다.

이후에도 에러가 발생하면 다음 서버로 순차 전환한다.

각 서버는 자신이 처리한 요청 로그를 자기 DB에 저장한다.

main 서버는 일정 주기(예: 10~20초)로 API 서버 로그를 수집하여 자신의 통합 로그 DB에 적재한다.

3. 추적 ID 정의

로그 추적은 아래 3단계 trace 구조로 관리한다.

3-1. program_trace_id

프로그램 실행 단위 식별자

프로그램 시작 시 1회 생성

프로그램이 종료될 때까지 변하지 않음

같은 실행에서 발생한 모든 요청은 동일한 program_trace_id를 가짐

즉, 사용자가 프로그램을 한 번 켠 실행 전체를 묶는 최상위 ID다.

3-2. api_trace_id

서버 전환 구간 단위 식별자

main 서버에서 시작할 때 최초 1개가 부여됨

이후 에러, 차단, 정책 변경 등으로 처리 서버가 바뀌는 시점에 새로운 api_trace_id로 변경됨

같은 서버 구간에서 계속 처리되는 동안에는 동일한 api_trace_id 유지

즉, api_trace_id는 서버가 바뀔 때 증가/변경되는 그룹 ID다.

예시:

main 서버에서 계속 성공 → 같은 api_trace_id

main 서버 실패 후 api 서버1 전환 → 새 api_trace_id

api 서버1에서 계속 성공 → 같은 api_trace_id

api 서버1 실패 후 api 서버2 전환 → 또 새 api_trace_id


3-3. request_trace_id

실제 호출 1회마다 새로 생성되는 식별자

요청을 보낼 때마다 항상 새 값이 발급됨

따라서 이전 호출과 같은 작업 흐름 안에 있더라도, 호출이 한 번 새로 발생하면 request_trace_id는 다시 바뀜

가장 하위 단위의 개별 호출 추적 ID로 사용한다

즉, request_trace_id는 “한 건 요청”을 묶는 ID가 아니라, 실제 호출 1번마다 매번 새로 생성되는 ID다.


4. 추가 로그 필드 정의
   4-1. user_id

해당 프로그램을 실행한 사용자 ID

로그 조회 시 사용자 기준 추적에 사용

4-2. attempt_no

하나의 논리적 요청을 처리하기 위해 몇 번째 서버 시도인지 나타내는 순번

최초 서버 호출은 1

실패하여 다음 서버로 넘기면 2

또 실패하여 다음 서버로 넘기면 3

같은 요청이 어느 서버에서든 최종 성공할 때까지 1씩 증가

새로운 다른 요청이 시작되면 다시 1부터 시작

즉, attempt_no는
“같은 요청을 처리하기 위해 서버를 몇 번째로 시도했는가”를 나타내는 값이다.

예시:

api1 호출 → attempt_no = 1

실패 후 api2 호출 → attempt_no = 2

실패 후 api3 호출 → attempt_no = 3

api3에서 성공

그 다음 다른 새로운 요청을 api3에서 다시 호출하면:

새 요청이므로 attempt_no = 1

즉, attempt_no는 현재 서버 기준 누적값이 아니라, 같은 요청 흐름 안에서만 증가하고, 다음 요청으로 넘어가면 초기화된다.

4-3. server_id

실제 요청을 처리한 서버 식별자

예: main, api1, api2, api3, api4

5. 전체 관계 구조

로그 계층은 아래와 같다.

program_trace_id > api_trace_id > request_trace_id

의미는 다음과 같다.

program_trace_id : 프로그램 실행 전체

api_trace_id : 그 실행 안에서 서버 전환 구간

request_trace_id : 각 구간 안의 개별 요청

이 구조를 사용하면 나중에 로그 분석 시 다음이 쉬워진다.

특정 프로그램 실행에서 전체 흐름 확인

어느 서버 구간에서 문제가 발생했는지 확인

어떤 요청이 몇 번째 재시도에서 실패했는지 확인

서버 전환 전후 맥락 비교

6. 동작 규칙
   6-1. 프로그램 시작 시

program_trace_id 생성

최초 api_trace_id 생성

현재 처리 서버는 main

6-2. 요청 처리 시

각 새로운 요청이 시작될 때

attempt_no = 1 로 시작

실제 호출 시마다 request_trace_id 새로 생성

현재 서버에 요청 수행

해당 서버는 자기 DB에 로그 기록

6-3. 서버 실패 후 다음 서버로 전환 시

같은 요청을 계속 처리하는 흐름이라면

서버가 바뀌면 api_trace_id 변경

다음 서버 호출 시 attempt_no 1 증가

실제 호출이 새로 발생하므로 request_trace_id는 새로 생성

server_id는 실제 호출한 서버 값으로 기록

핵심은 다음이다.

request_trace_id는 호출할 때마다 항상 새로 생성

attempt_no는 같은 요청 흐름 안에서 서버 전환 시 1씩 증가

새로운 다른 요청이 시작되면 attempt_no는 다시 1부터 시작

6-4. 서버 전환 시

새로운 api_trace_id 발급

server_id 변경

이후 요청은 새 api_trace_id 기준으로 기록

핵심은 다음이다.

프로그램이 안 바뀌면 program_trace_id는 유지

서버가 바뀌면 api_trace_id는 변경

요청이 새로 시작되면 request_trace_id는 새로 생성

같은 요청을 다시 시도하면 attempt_no만 증가

7. 서버별 로그 저장 방식

모든 서버는 요청을 처리할 때 자신의 DB에 로그를 저장한다.

즉,

main 서버는 main DB에 저장

api1 서버는 api1 DB에 저장

api2 서버는 api2 DB에 저장

api3 서버는 api3 DB에 저장

api4 서버는 api4 DB에 저장

이렇게 하면 각 서버는 독립적으로 자신의 처리 이력을 남길 수 있다.

8. 메인 서버 통합 수집 방식

main 서버는 스케줄러를 통해 API 서버 로그를 주기적으로 가져온다.

예시:

10초 또는 20초 주기

api1 ~ api4 로그 조회 API 호출

신규 로그만 main 통합 로그 DB에 insert

이 방식의 목적은 다음과 같다.

메인 서버에서 전체 로그를 한 번에 조회 가능

장애 분석 시 API 서버마다 직접 들어가지 않아도 됨

운영 모니터링 단일화 가능

9. 중복 적재 방지

main 서버가 API 서버 로그를 수집할 때는 중복 적재 방지 키가 필요하다.

그 이유는 같은 로그를 여러 번 가져올 수 있기 때문이다.

중복 방지 방식은 아래 중 하나로 잡으면 된다.

방식 1. 원본 로그 고유 키 사용

각 서버 로그 테이블의 PK 또는 고유 로그 ID를 함께 저장

예:

source_server_id

source_log_id

그리고 main 통합 로그 테이블에서
(source_server_id, source_log_id)를 unique로 둔다.

방식 2. 복합 유니크 키 사용

다음 같은 컬럼 조합을 unique로 둘 수 있다.

program_trace_id

api_trace_id

request_trace_id

attempt_no

server_id

실무적으로는 원본 로그 ID 방식이 가장 안전하다.

10. 권장 로그 컬럼

최소한 아래 컬럼은 두는 것을 권장한다.

id

user_id

program_trace_id

api_trace_id

request_trace_id

attempt_no

server_id

request_url

request_method

request_payload

response_code

response_body

success_yn

error_code

error_message

created_at

추가로 있으면 좋은 컬럼:

job_name

item_key

elapsed_ms

bot_detected_yn

switch_reason

source_server_id

source_log_id

collected_at

11. 예시 시나리오
    프로그램 실행 시작

program_trace_id = P202603130001

api_trace_id = A202603130001

현재 서버 = main

요청 A 시작

첫 호출:

request_trace_id = R202603130001

attempt_no = 1

server_id = api1

실패

두 번째 서버 시도:

request_trace_id = R202603130002

attempt_no = 2

server_id = api2

실패

세 번째 서버 시도:

request_trace_id = R202603130003

attempt_no = 3

server_id = api3

성공

요청 B 시작

다음 다른 요청은 새 요청이므로 다시 시작:

request_trace_id = R202603130004

attempt_no = 1

server_id = api3

즉,

request_trace_id는 호출할 때마다 계속 바뀌고

attempt_no는 같은 요청 안에서만 1, 2, 3으로 증가하며

다음 요청이 시작되면 다시 1부터 시작한다

12. 최종 정리

이 구조의 핵심은 아래와 같다.

1) program_trace_id

프로그램 실행 전체를 묶는 최상위 ID
프로그램 시작 시 1회 생성, 종료 전까지 유지

2) api_trace_id

서버 전환 구간 ID
서버가 바뀔 때마다 새로 생성

3) request_trace_id

개별 요청 1건 ID
요청마다 새로 생성

4) attempt_no

같은 요청 안에서 재시도 순번
1부터 시작하여 재시도 시 증가

5) server_id

실제 요청을 처리한 서버

6) 로그 저장 정책

각 서버는 자기 DB에 로그 저장

7) 로그 수집 정책

main 서버는 스케줄러로 API 서버 로그를 주기 수집하여 통합 DB 적재

8) 중복 방지

main 통합 적재 시 원본 로그 고유 키 또는 복합 유니크 키로 중복 insert 방지


