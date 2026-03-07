24.12.10
특별한꿀벌6962

https://drive.google.com/file/d/1w5F9E7KYLJJ7TIkZ_XADRSZsqr9ZO9uy/view?pli=1
https://drive.usercontent.google.com/download?id=1w5F9E7KYLJJ7TIkZ_XADRSZsqr9ZO9uy&export=download&authuser=0
다운로드




첨부파일에 설명드렸지만 아티스트 페이지에 노출되지 않아 크롤링이 불가하니 특정 url 을 최소 1~ 최대 입력후 해당 작가를 크롤링 을 순서데로 진행하는 방식이면 됩니다.

18:49


예시
크롤링 URL입력 방식 예시:
하단과 같이 6개의 URL을 한번에 입력하면 각 URL 페이지가 반복해서 크롤링 되어야 합니다.

https://artvee.com/artist/michelangelo/
https://artvee.com/artist/william-bouguereau/
https://artvee.com/artist/john-william-godward/
https://artvee.com/artist/jean-leon-gerome/
https://artvee.com/artist/evelyn-de-morgan/
https://artvee.com/artist/anthony-van-dyck/


pyinstaller
PyInstaller는 파이썬 스크립트를 독립 실행형 실행 파일(EXE)로 변환해주는 도구입니다.
이 명령어는 PyInstaller를 실행하여 main.py라는 파이썬 파일을 EXE 파일로 빌드합니다.

--distpath dist
--distpath 옵션은 빌드된 EXE 파일과 해당 실행에 필요한 다른 파일들을 저장할 폴더를 지정합니다.
기본적으로, PyInstaller는 dist 폴더를 사용하지만 이 옵션을 통해 경로를 지정할 수 있습니다.
dist 폴더는 EXE 파일이 생성되는 최종 출력 폴더입니다.
예시: dist/main 폴더에 EXE 파일이 생성됩니다.



https://artvee.com/c/abstract/



python -m PyInstaller --clean --noconfirm --onefile `
--icon=resources\icons\crawling.ico `
--hidden-import=deep_translator `
--hidden-import=selenium `
--hidden-import=selenium.webdriver `
--hidden-import=selenium.webdriver.chrome `
--hidden-import=selenium.webdriver.chrome.service `
--hidden-import=selenium.webdriver.chrome.options `
--hidden-import=selenium.webdriver.common `
--collect-all selenium `
--collect-all deep_translator `
main.py