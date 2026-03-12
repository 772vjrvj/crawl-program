■ 2026-03-12

저장 파일이 이름이 이상함
실제 상품명으로 저장되도록 수정함 h1 태그 사용












■ 2026-01-08

날짜 : 2026-01-08  
고객 : K6507677452
거래금액 : 0
버전 : 3.0.0

윈11에서 기존 버전 경로가 이상함 src안으로 가는 문제가 있었음 개발환경에서
그리고 onedrive의심됨

코드 수정하여 배포 완료

안녕하세요!
최근 만들어주신 크롤링 프로그램 잘 사용중이었는데요!
아무것도 변동된 사항이 없는데 갑자기 크롤링된 엑셀 파일이 저장되지 않습니다.
크롤링까지는 완료되었다고 뜨는데 원래는 기존에 output_lululemon에 저장되었는데 지금 파일이 저장되지 않아 찾을 수 없는 상황입니다.
보내주신 파일을 다시 다운받아 압출 풀고 다시 설치해봤지만 작동되지 않는데 확인해주실 수 있으실까요?

[2026-03-03 10:16:32] 엑셀 데이터 갯수 : 4
[2026-03-03 10:16:32] {'url': 'https://shop.lululemon.com/en-ca/p/womens-leggings/Wunder-Train-HR-Crop-21/_/prod9750277?color=53503';, 'file': 'url_list'}
[2026-03-03 10:16:32] {'url': 'https://shop.lululemon.com/en-ca/p/womens-leggings/Wunder-Train-HR-Tight-25/_/prod9750215?color=0001';, 'file': 'url_list'}
[2026-03-03 10:16:32] {'url': 'https://shop.lululemon.com/en-ca/p/womens-leggings/Wunder-Train-HR-Tight-28/_/prod10440258?color=26083';, 'file': 'url_list'}
[2026-03-03 10:16:32] {'url': 'https://shop.lululemon.com/en-ca/p/womens-leggings/Wunder-Train-HighRise-Crop-23/_/prod10370399?color=0001';, 'file': 'url_list'}
[2026-03-03 10:16:35] 초기화 성공
[2026-03-03 10:16:35] 크롤링 시작
[2026-03-03 10:16:37] [SKIP] ProductGroup 없음: https://shop.lululemon.com/en-ca/p/womens-leggings/Wunder-Train-HR-Crop-21/_/prod9750277?color=53503
[2026-03-03 10:16:37] [옵션 미리보기] 옵션 없음 (0건)
[2026-03-03 10:16:37] (1/4) 저장완료: C:\Users\chuls\OneDrive\Desktop\룰루레몬v2\룰루레몬v2\output_lululemon\product_20260303_101637.xls
[2026-03-03 10:16:41] [SKIP] ProductGroup 없음: https://shop.lululemon.com/en-ca/p/womens-leggings/Wunder-Train-HR-Tight-25/_/prod9750215?color=0001
[2026-03-03 10:16:41] [옵션 미리보기] 옵션 없음 (0건)
[2026-03-03 10:16:41] (2/4) 저장완료: C:\Users\chuls\OneDrive\Desktop\룰루레몬v2\룰루레몬v2\output_lululemon\product_20260303_101641.xls
[2026-03-03 10:16:45] [SKIP] ProductGroup 없음: https://shop.lululemon.com/en-ca/p/womens-leggings/Wunder-Train-HR-Tight-28/_/prod10440258?color=26083
[2026-03-03 10:16:45] [옵션 미리보기] 옵션 없음 (0건)
[2026-03-03 10:16:45] (3/4) 저장완료: C:\Users\chuls\OneDrive\Desktop\룰루레몬v2\룰루레몬v2\output_lululemon\product_20260303_101645.xls
[2026-03-03 10:16:51] [SKIP] ProductGroup 없음: https://shop.lululemon.com/en-ca/p/womens-leggings/Wunder-Train-HighRise-Crop-23/_/prod10370399?color=0001
[2026-03-03 10:16:51] [옵션 미리보기] 옵션 없음 (0건)
[2026-03-03 10:16:51] (4/4) 저장완료: C:\Users\chuls\OneDrive\Desktop\룰루레몬v2\룰루레몬v2\output_lululemon\product_20260303_101651.xls
[2026-03-03 10:16:55] 메인 성공
[2026-03-03 10:16:55] =============== 크롤링 종료
[2026-03-03 10:16:55] 종료 완료



pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "LULULEMON" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\lululemon\version_info.txt" `
--distpath ".\dist" `
--hidden-import "src.workers.main.api_lululemon_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl