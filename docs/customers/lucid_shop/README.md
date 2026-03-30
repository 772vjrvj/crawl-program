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
	
	sudo chown -R bitnami:daemon /home/bitnami/htdocs/data/item/lucidshop
	find /home/bitnami/htdocs/data/item/lucidshop -type d -exec chmod 2775 {} \;
	find /home/bitnami/htdocs/data/item/lucidshop -type f -exec chmod 644 {} \;

	
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

	
