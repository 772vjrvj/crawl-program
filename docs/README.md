1. Powershell 관리자 권한 실행 

2. git config --global --add safe.directory E:\git\php_crawling

3. 인텔리제이 재부팅 

4. .gitignore 추가

5. 3.11 가상환경 생성
   py -3.11 -m venv venv

6. 가상환경 활성화 > (venv) PS E:\git\crawl-program 확인 완료
   .\venv\Scripts\Activate.ps1

7. pip 최신화
   python -m pip install --upgrade pip

8. pip 버전 확인 : pip 26.0.1 from E:\git\crawl-program\venv\Lib\site-packages\pip (python 3.11)
   pip --version

9. 인텔리제이 세팅
   Proejct Settings > Project > SDK J > Add SDK > Python SDK
   이미 가상환경을 만들었으므로
   Virtualenv Enviroment > Existing enviroment 에서 E:\git\crawl-program\venv\Scripts\python.exe 선택

10. 세팅 확인
   View → Tool Windows → Python Console 에서
   
   import sys
   print(sys.executable)
   입력후 엔터 치면

   E:\git\crawl-program\venv\Scripts\python.exe 
   확인

11. 실행 환경
    root 경로에 main.py 파일만든다
    우측 상단에 Edit Configurations > Run/Debug configuration > Add new run configuration > Python 선택
    Use specified interpreter: Python 3.11 (crawl-program venv)
    script : E:/git/crawl-program/main.py
    Working directory : E:/git/crawl-program
    나머지는 기본



■ 트리구조 확인
python tools/tree/print_tree.py --include .py .js .ts --depth 6


■ requirements.txt 만들기
pip freeze > requirements.txt


■ requirements 사용
pip install -r requirements.txt


■ 빌드
pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "CrawlProgram" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_naver_band_member_set_worker" 


■ 빌드 설명
pyinstaller .\main.py `                    # 시작 파일 (엔트리 포인트)
--noconfirm `                              # 기존 build/dist 폴더 덮어쓰기 확인 없이 진행
--clean `                                  # 이전 빌드 캐시 제거 후 새로 빌드
--windowed `                               # 콘솔창 없이 GUI 프로그램으로 빌드
--name "CrawlProgram" `                    # 생성될 exe 이름
--icon ".\resources\icons\crawling.ico" `  # exe 아이콘 설정
--version-file ".\version_info.txt" `      # 버전 정보
--distpath ".\dist" `                      # 결과물 저장 위치 (dist 폴더)
--workpath ".\build" `                     # 빌드 중간 파일 저장 위치 (build 폴더)
--collect-all PySide6 `                    # PySide6 관련 리소스/플러그인 전체 포함 (UI 오류 방지) 현재 사용 안함
--hidden-import "src.workers.main."        # 동적 import 되는 워커 모듈 강제 포함 (importlib 사용 대응)


■ 빌드 후
runtime에 해당 worker 폴더 이동 app.json이동
resources 통째로 이동