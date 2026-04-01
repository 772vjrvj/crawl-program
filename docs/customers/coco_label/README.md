우선은 세가지 크롤링이 필요하며
크롤링 프로그램은 일회용으로 예상됩니다

이미지는 따로 다시 보내드릴 예정입니다!

완벽하게 데이터가 이전되면 프로그램은 크게 후로 필요없을 것으로 생각됩니다!!

혹시 직접 크롤링업로드도 가능하신지도 궁금합니다!

총 세가지가 필요합니다

1. A사이트 의 관리자에서
   B사이트의 관리자 페이지로 상품을 크롤링하여 재업로드

2. 크롤링된 상품을 토대로 a사이트의 상품사진 게시판의 이름을 검색해 크롤링된 b 사이트에 상품을 검색해
   B 사이트의 상품사진 게시판에 재업로드

3.2번과 유사하게 a사이트의 리뷰를 검색해 b사이트의 상품리뷰에 작성입니다




1. 전체상품입니다.

2. FTP 계정정보 제공 가능합니다 또는 관리자 아이디 제공가능합니다.
   다만 a사이트는 ftp가 접속불가합니다.
   b사이트는 접속 가능합니다.

3. 업로드할 갯수는 예상입니다
1) 상품 업로드 약 3만개
2) 상품 게시물 약 1700개
3) 상품 리뷰 약 8000개



요청사항1.
asite : coco-label.com (이전 사이트)
bsite : rico2.co.kr (대상 사이트)
단 bsite는 예시라서 추후 만들어질 사이트랑 비슷하긴하나 확실한 사이트는 아직 아닙니다.

요청사항2.
이것은 이미지 보내드리면서 같이 정리해드리겠습니다

요청사항3.
asite ftp 제공 불가 (카페24, 아임웹, 공유 쇼핑몰 호스팅)
bsite ftp 제공 가능 (AWS 개인 사설 서버, 그누보드 환경)
가능하다면 sql 작업해서 엑셀로 올릴수는있으나 조금 어려울것같아 조심스럽습니다.


1. 상품 수량은 약 2만개입니다.
2. 상세페이지에 있는 실제 이미지의 수는 견적서 내용대로 많아질 가능성이 높습니다.
3. 업로드/이관 작업이 말씀하시는 프로그램 별도로 직접 크롤링 돌려주시는 비용일까요?
4. 웹 분석형 크롤링이라면 파이썬으로 html 요소 분석해서 직접 하나하나 집어가면서 하셔야하는 작업이 맞을까요? 제가 지식이 없어서 설명해주시면 감사합니다.
5. 부가세는 세금계산서를 신청하면 붙을까요? 세금 계산서도 가능할까요?



b 사이트 다른곳으로 바꿔드릴게요! 이 사이트에는 직접 테스트 해보셔도되긴합니다. 운영중 x

계정 정보 및 접속 주소
https://edenwatch.co.kr
https://edenwatch.co.kr/bbs/login.php
id : admin
ps : 1234


a site : FTP 없습니다

계정 정보 및 접속 주소
https://coco-label.com/
https://coco-label.com/admin

id : cocolabel777@gmail.com
ps : Cocofpvmf0324@!


184.168.118.223
mz7s7k5o7nhc
Flzhdlqslek1!
소스 경로 /public_html/edenwatch



01086182277 





새 사이트 급하게 개설되었습니다. 카테고리는 아직 작업안되었으며 실질적으로 업로드 해주셔도 됩니다!!
도메인이 없지만 접속가능합니다!
https://13.125.228.230/

ID admin
PS 1234


파일 질라   FileZilla (SFTP)
프로토콜   SFTP
호스트   13.125.228.230
사용자   bitnami
키파일   .pem
비밀번호   비밀번호는 쓰지 않음




# =============================================================

■ 이미지 업로드

SFTP 접속

파일 질라   FileZilla (SFTP)
프로토콜   SFTP
호스트   13.125.228.230
사용자   bitnami
키파일   .pem
비밀번호   비밀번호는 쓰지 않음
/opt/bitnami/apache/htdocs/data/item


■ 매핑관계

키워트
가방, 지갑, 의류, 신발, 잡화, 명품 시계, 샤넬 프리미엄, 에르메스 프리미엄, 남성, SALE (당일발송)


A ->  B

가방                -> 여성 가방
지갑               -> 여성 지갑
의류               -> 여성 의류
신발               -> 여성 신발
잡화               -> 여성 패션 잡화
명품 시계           -> 명품 시계
샤넬 프리미엄        -> 샤넬 프리미엄 
에르메스 프리미엄     -> 에르메스 프리미엄
남성 > 남성 가방     -> 남성 가방
남성 > 남성 신발     -> 남성 신발
남성 > 남성 의류     -> 남성 의류
남성 > 남성 지갑     -> 남성 지갑
남성 > 남성 패션 잡화 -> 남성 패션 잡화
남성 > 크롬하츠      -> 크롬하츠
SALE (당일발송)     -> SALE (당일발송)





■ 크롤링 업로드할 사이트(고객 사이트)
상품 페이지 : https://lucidshop.kr/
계정 : admin / aura1004!
관리자 페이지 : https://lucidshop.kr/adm/
관리자 계정 : admin / aura1004!
상품관리 페이지 : https://lucidshop.kr/adm/shop_admin/itemlist.php

■ 크롤링할 사이트
사이트 : https://midomae.com/
계정 astierceo@gmail.com / Aura1004!

■ SFTP
주소 : 15.164.81.154
아이디 : bitnami
방식 : 키파일



■ SFTP 권한

	chown -R bitnami:daemon
	→ 소유자/그룹 맞춤

	디렉토리 2775
	→ 폴더는 쓰기 가능 + setgid라서 새로 생기는 하위 폴더/파일이 그룹 daemon 유지에 도움

	파일 644
	→ 웹에서 읽기 가능, 불필요한 실행권한 없음

	
	권한 설정
	
	mkdir -p /home/bitnami/htdocs/data/item/고객폴더명
	sudo chown -R bitnami:daemon /home/bitnami/htdocs/data/item/고객폴더명
	find /home/bitnami/htdocs/data/item/고객폴더명 -type d -exec chmod 2775 {} \;
	find /home/bitnami/htdocs/data/item/고객폴더명 -type f -exec chmod 644 {} \;
	
	sudo chown -R bitnami:daemon /home/bitnami/htdocs/data/item/d0
	find /home/bitnami/htdocs/data/item/d0 -type d -exec chmod 2775 {} \;
	find /home/bitnami/htdocs/data/item/d0 -type f -exec chmod 644 {} \;


	폴더 추가후 진행
	sudo chown -R bitnami:daemon /opt/bitnami/apache/htdocs/data/item/lucidshop/mensclothing
	find /opt/bitnami/apache/htdocs/data/item/lucidshop/mensclothing -type d -exec chmod 2775 {} \;
	find /opt/bitnami/apache/htdocs/data/item/lucidshop/mensclothing -type f -exec chmod 644 {} \;

	
	

	확인
	
	ls -ald /home/bitnami/htdocs/data/item/lucidshop
	ls -ald /home/bitnami/htdocs/data/item/lucidshop/womensclothing
	ls -al /home/bitnami/htdocs/data/item/lucidshop/womensclothing | head


	여기서 이렇게 나오면 정상에 가까워요.

	폴더: drwxrwsr-x 또는 drwxrwxr-x

	파일: -rw-r--r--

	소유권: bitnami daemon

	2775를 주면 폴더는 앞에 s가 보일 수 있어요.
	예: drwxrwsr-x
	
	
	*** 폴더 추가 이미지 추가 후에는 꼭 위과정을 다시 해줘야 한다.



■ SSH
MobaXterm > Session > SSH

	□ Basic SSH settings
		- Remote host      : 15.164.81.154       ✅ 맞음 (EC2 공인 IP)
		- Specify username : bitnami             ✅ 맞음 (Lightsail 기본 사용자)
		- Port             : 22                  ✅ 기본 SSH 포트

	□ Advanced SSH settings
		- Use private key  : LightsailDefaultKey-ap-northeast-2.ppk


■ 이미지 저장 경로
기본 경로 : /opt/bitnami/apache/htdocs/data/item
기본 경로 : /opt/bitnami/apache/htdocs/data/item	/image/test.jpg

	여기 하위에 등록
	이미지1에는 image/test.jpg 이렇게 넣기만 하면됨


■ 옵션
S M L XL XXL

	남성 g0 여성 f0

■ 무조건 2개 테스트 하고 넣기
이게 제일 중요


■ 빌드
pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "COCO_LABEL" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\coco_label\version_info.txt" `
--distpath ".\dist" `
--add-data ".\resources\customers\coco_label\json;resources\customers\coco_label\json" `
--hidden-import "src.workers.main.api_coco_label_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl
