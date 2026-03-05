KRX + NEXTRADE 통합 거래대금 리포트 프로그램
프로젝트 정보

고객 : 사랑스러운지식인943
거래일시 : 2026.01.06
거래금액 : 150,000원
프로그램 : KRX + NEXTRADE 거래대금 리포트

프로그램 개요

본 프로그램은 KRX(한국거래소) 와 NEXTRADE(넥스트레이드) 데이터를 수집하여
종목별 거래대금을 합산한 후 사용자가 설정한 거래대금 + 등락률 조건에 맞는 종목을 자동으로 추출하는 프로그램입니다.

데이터 수집 대상

KRX : 한국거래소
NXT : 넥스트레이드

거래대금 계산 방식
최종 거래대금 = KRX 거래대금 + NEXTRADE 거래대금
데이터 수집 구조
KRX 데이터

사이트 :
https://data.krx.co.kr

실제 데이터 API :

POST
https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd

요청 파라미터

시장구분 : 전체
조회일자 : YYYYMMDD
종목구분 : 전체

주요 데이터 컬럼

종목명 : ISU_ABBRV
종목코드 : ISU_SRT_CD
등락률 : FLUC_RT
거래대금 : ACC_TRDVAL

NEXTRADE 데이터

사이트 :
https://www.nextrade.co.kr/menu/transactionStatusMain/menuList.do

실제 데이터 API :

POST
https://www.nextrade.co.kr/brdinfoTime/brdinfoTimeList.do

요청 파라미터

시장구분 : 전체
조회일자 : YYYYMMDD
페이지 : pageIndex

주요 데이터 컬럼

종목명 : isuAbwdNm
종목코드 : isuSrdCd
등락률 : upDownRate
거래대금 : accTrval

데이터 처리 로직

프로그램은 다음 과정을 통해 데이터를 분석합니다.

1. KRX 데이터 수집
   fetch_krx()
2. NEXTRADE 데이터 수집
   fetch_nextrade()
3. 종목 코드 기준 데이터 병합
   KRX 종목코드
   NXT 종목코드
   → 코드 기준 매칭
4. 거래대금 합산
   최종 거래대금
   = KRX 거래대금 + NXT 거래대금
5. 종목 정렬
   거래대금 합계 기준 내림차순 정렬
6. 순위 생성
   거래대금 기준 순위 생성
   필터 조건

프로그램에는 두 개의 조건 필터가 존재합니다.

조건1
[조건1] 거래대금 >= 설정값
AND
[조건1] 등락률 >= 설정값

예시

거래대금 : 1000억 이상
등락률 : 3% 이상
조건2
[조건2] 거래대금 >= 설정값
AND
[조건2] 등락률 >= 설정값

예시

거래대금 : 3000억 이상
등락률 : 5% 이상


"worker_class": "src.workers.main.api_krx_nextrade_brand_set_worker:ApiKrxNextradeSetLoadWorker",


■ 빌드
pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "KRX NEXTRADE" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\krx_nextrade_brand\version_info.txt" `
--distpath ".\dist" `
--hidden-import "src.workers.main.api_krx_nextrade_brand_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl