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
    