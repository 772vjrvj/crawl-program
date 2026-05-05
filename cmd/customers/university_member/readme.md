



■ 항상 조직도를 제일 먼저 본다.

작업 팁
■ 학과 행정 메일
1. 학과 내 조직도 행정팀 탭에서 이메일 추출
2. 학과 홈페이지 footer에 이메일 확인
3. 학과 오시는 길
4. 게시판에서 모든 글에서 @koreauniv.co.kr을 포함하면서 교수랑을 다른 이메일을 찾고 작성자를 이름으로 한다.

■ 대학/대학원

대학/대학원 기본 4만 -> 작업이 너무 힘듬
탭 추가 1만...(산악협력)
게시판에서 찾는 경우 추가 1만
학과 홈페이지이가 공통이 아닌 경우 추가 2만






2차
2026-05-02

개발자에게 전달할 **‘크롤링용 시드 URL(Seed URLs)’** 목록입니다. 요청하신 7개 대학의 서울캠퍼스를 기준으로, 모든 단과대, 대학원, 연구소, 부설기관의 링크가 집약된 **색인(Index) 페이지** 위주로 정리했습니다.
개발자는 이 페이지들을 시작점으로 삼아 하위 링크를 탐색(Traversing)하며 조직별 연락처와 이메일을 수집할 수 있습니다.



### 1. 동국대학교 (서울캠퍼스) V 완벽 게시판 까지 커버
* **대학(학부):** https://www.dongguk.edu/page/77 (단과대 및 학과 목록)
* **대학원:** https://www.dongguk.edu/page/113 (일반/전문/특수대학원 전체)
* **연구소/기관:** https://www.dongguk.edu/page/127 (부설연구소 및 부속기관 통합)


### 2. 서경대학교 V
* **대학/대학원:** https://www.skuniv.ac.kr/college_main (학부 및 대학원 통합 페이지)
* **부설기관/연구소:** https://www.skuniv.ac.kr/annex_main (부속기관 및 부설연구소 목록)
추가X


### 3. 한성대학교 V
* **대학(학부):** https://www.hansung.ac.kr/hansung/1449/subview.do (단과대별 구성)
* **대학원:** https://www.hansung.ac.kr/hansung/1544/subview.do (대학원 목록)
* **연구소/기관:** https://www.hansung.ac.kr/hansung/1553/subview.do (연구소 및 부속기관)


### 4. 한양대학교 (서울캠퍼스)
* **대학(학부):** https://www.hanyang.ac.kr/web/www/-66 (서울캠퍼스 단과대별 학과 목록)
* **대학원:** https://www.hanyang.ac.kr/web/www/-67 (일반/전문/특수대학원)
* **연구기관:** https://www.hanyang.ac.kr/web/www/-88 (연구소 검색 및 목록)
* **부속기관:** https://www.hanyang.ac.kr/web/www/-81 (서울캠퍼스 주요 센터 및 부속기구)


### 5. 광운대학교 V 완벽 게시판 까지 커버
* **대학(학부):** https://www.kw.ac.kr/ko/univ/univ_index.jsp (단과대 및 전공 목록)
* **대학원:** https://www.kw.ac.kr/ko/univ/grad_index.jsp (대학원 종류별 링크)
* **연구기관/부설기구:** https://www.kw.ac.kr/ko/univ/research_index.jsp (부설연구소 및 교내 부속기관)


### 6. 서울과학기술대학교 (서울과기대) V
* **대학/대학원:** https://www.seoultech.ac.kr/univ/univ/intro/ (대학 및 대학원 통합 안내)
* **부속/부설기관:** https://www.seoultech.ac.kr/univ/adjunct/intro/ (센터, 연구소 등 부속시설 목록)
추가1만


### 7. 서울여자대학교 V
* **대학(학부):** https://www.swu.ac.kr/www/univ01_01_01.html (단과대 및 전공)
* **대학원:** https://www.swu.ac.kr/www/univ02_01.html (대학원 안내)
* **연구소/부속기관:** https://www.swu.ac.kr/www/univ03_01_01.html (부속기관 및 연구소)
추가2만



### 개발자를 위한 크롤링 팁 (전달용)
1. **Depth 설정:** 위 URL들은 1단계 페이지입니다. 각 링크를 클릭해 들어가는 2단계(학과/연구소 메인), 3단계(교수진/조직도/연락처 페이지)까지 탐색하도록 설정이 필요합니다.
2. **키워드 필터링:** 이메일을 찾을 때 페이지 내에서 mailto: 태그를 우선적으로 수집하거나, Contact, Professor, Organization, Office, 연락처, 조직도, 구성원 소개 등의 메뉴를 추적하는 로직이 유효합니다.
3. **도메인 제한:** 서울캠퍼스 데이터만 필요한 경우, 한양대(ERICA)나 동국대(WISE) 등 분교 도메인이 포함되지 않도록 필터링 규칙을 세워야 합니다.



1. 조직도에 들어간다.
2. 학과 사이트 목록을 가져온다.
3. 학부별 맨앞 학과들을 10개 정도를 보면서 일반화되어 보이는 사이트를 코드로 짜서 실행한다.
4. 예외 case 위에서 안걸리는 것들은 예외 case로 하고 별도 반수동으로 작업한다.
5. 자동으로 걸러진 것들, 예외는 각각 py파일로 별도로 빼서 하는게 좋다. 한 파일에 다 모여있으면 분류가 안된다.
6. 엑셀에 적으면서 하나씩 진행해라 완벽한 자동은 없다.
7. 위 작업으 끝나면 완료본과 중복 제거본을 만들면 된다.


홈페이지를 보고
보편화된 사이트라고 판단