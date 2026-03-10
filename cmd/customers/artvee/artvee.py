import json
import os
import random
import re
import ssl
import sys
import time
import traceback
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from selenium import webdriver
from tqdm import tqdm
import logging
from datetime import datetime
import builtins


# 현재 디렉터리에 있는 다른 파일을 import하려면 sys.path.append("./")를 추가해야 해당 파일을 찾을 수 있습니다.
sys.path.append("./")

# SSL 인증서 검증을 건너뜀
ssl._create_default_https_context = ssl._create_unverified_context


# ✅ 글로벌 영역에 백업
original_print = builtins.print


def init_logger():
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"{today}.log")

    # ✅ 콘솔 출력을 중복 방지하기 위해 StreamHandler 제거
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(filename)s:%(lineno)d - %(funcName)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8")
        ]
    )

    # ✅ print()를 logging.info() + 콘솔 출력으로 덮기
    def dual_print(*args, **kwargs):
        msg = " ".join(str(arg) for arg in args)
        logging.info(msg, stacklevel=2)  # 👈 호출자 기준 라인으로 기록
        original_print(*args, **kwargs)
    builtins.print = dual_print

    # ✅ original_print를 다른 모듈에서도 사용 가능하게 전역 등록
    globals()["original_print"] = original_print

# === 신규 === None 방어용 텍스트 유틸
def safe_text(el, default=""):
    return el.get_text(strip=True) if el else default

# === 신규 === soup.find() 결과 None 방어
def safe_find_text(soup, tag, class_=None, default=""):
    el = soup.find(tag, class_=class_)
    return safe_text(el, default=default)


class ARTVEE:
    def __init__(self) -> None:
        self.baseUrl = "https://artvee.com/"
        self.sess = requests.Session()

    def login(self)->dict:
        webdriver_options = webdriver.ChromeOptions()
        webdriver_options.add_argument('--disable-blink-features=AutomationControlled')
        webdriver_options.add_argument("--start-maximized")
        webdriver_options.add_argument("headless")
        webdriver_options.add_experimental_option('useAutomationExtension', False)
        webdriver_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        webdriver_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.driver = webdriver.Chrome(options=webdriver_options)
        self.driver.set_page_load_timeout(120)
        self.driver.get("https://artvee.com/")
        cookies = self.driver.get_cookies()
        for cookie in cookies:
            self.sess.cookies.set(cookie['name'], cookie['value'])
        self.version = self.driver.capabilities["browserVersion"]
        self.headers = {
            "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{self.version}"
        }
        self.driver.quit()
        return self.headers

    def getArtistsUrlList(self) -> list[dict]:
        artistsUrlList:list[dict] = []
        totalCount = 1
        i = 1
        while 1:
            url:str = f"{self.baseUrl}artists/page/{i}/"
            res:requests.Response = self.sess.get(url,headers=self.headers)
            time.sleep(random.uniform(0.3, 0.5))

            # 비정상 응답이면 종료
            if res.status_code != 200:
                print(f"artists 목록 페이지 응답코드 비정상 : {url} / status={res.status_code}")
                break

            i += 1

            soup = BeautifulSoup(res.content,"html.parser")
            allArtist = soup.find_all("div",class_="wrapp-catti")
            if len(allArtist) ==0:
                break
            for artistInfo in allArtist:
                artistUrl = artistInfo.find("a")["href"]
                artistcount = artistInfo.find("mark", class_="count").text.strip()
                artistsUrlList.append({"artistUrl":artistUrl,"artistcount":artistcount,"page":(i-1),"totalCount":totalCount})
                totalCount+=1

        return artistsUrlList

    def getExcelArtistsUrlList(self, file_path) -> list[dict]:
        artistsUrlList: list[dict] = []

        # 엑셀 파일 읽기
        df = pd.read_excel(file_path)

        # 'artist_list' 컬럼에서 URL들을 추출하여 리스트로 변환
        url_list = df['artist_list'].tolist()
        print(f'artist_list : {url_list}')

        # URL 목록을 artistsUrlList에 추가
        totalCount = 1
        for i, artistUrl in enumerate(url_list, start=1):
            artistsUrlList.append({
                "artistUrl": artistUrl,
                "artistcount": '0',  # 엑셀 파일에 'artistcount' 정보가 없으므로 임시로 'N/A'를 설정
                "page": 0,  # 페이지 번호는 URL 순서대로 설정
                "totalCount": totalCount
            })
            totalCount += 1

        return artistsUrlList

    def extractCollectionExcelInfo(self,df:pd.DataFrame,df_data:pd.DataFrame,collectionUrl:str,category:str) -> list[pd.DataFrame]:
        i = 1
        totalCount = 1
        totalImageInfoList:list[dict] = []
        artist_count_dict = {}
        while 1:
            url = f"{collectionUrl}page/{i}?&per_page=70"
            try:
                res = requests.get(url,headers=self.headers)
            except:
                time.sleep(10)
                print(f"사이트 오류로 인한 넘김 : {url}")
                i+=1
                continue
            if res.status_code != 200:
                break

            time.sleep(random.uniform(0.45, 0.55))
            soup = BeautifulSoup(res.content,"html.parser")
            if soup.find("div",class_="entry-content") != None or str(soup).find("Sorry, we can't seem to find the page you're looking for") != -1:
                break
            i += 1
            collectionName = soup.find("h1",class_="entry-title").text.strip()
            titlwrap = soup.find('div', class_='titlwrap')
            artistDescription = ""
            if titlwrap:
                containers = titlwrap.find_all('div', class_='container')
                for container in containers:
                    p = container.find('p')
                    if p:
                        artistDescription = p.get_text(strip=True)
                        break  # 첫 번째 <p> 텍스트만 원할 경우

            infoList = soup.find_all("div",class_="pbm")

            total = soup.find("p",class_="woocommerce-result-count").text.replace("items","").strip()


            for index, infoData in enumerate(infoList, start=1):
                brand_div = infoData.find('div', class_='woodmart-product-brands-links')
                country = ""
                artistName = ""
                country_years = ""
                if brand_div:
                    match = re.search(r'\(([^)]+)\)', brand_div.text)
                    if match:
                        country_years = match.group(1)  # 'Norwegian, 1911 - 1992'
                        country = country_years.split(',')[0].strip()  # 'Norwegian'

                    a_tag = brand_div.find('a')
                    if a_tag:
                        artistName = a_tag.get_text(strip=True)

                key = artistName if artistName else "작가명 없음"
                artist_count_dict[key] = artist_count_dict.get(key, 0) + 1


                div = infoData.find("div", class_="woodmart-product-cats")
                field = div.text.strip() if div else ""
                data = infoData.find("div")
                idData = data["data-id"].strip()
                sizeData = json.loads(data["data-sk"])
                imgInfo = sizeData["sk"]
                try:
                    standard = sizeData["sdlimagesize"].split("px")[0].split("x")
                    standardX = standard[0].strip()
                    standardY = standard[1].strip()
                except:
                    standardX = ""
                    standardY = ""
                try:
                    max = sizeData["hdlimagesize"].split("px")[0].split("x")
                    maxX = max[0].strip()
                    maxY = max[1].strip()
                except:
                    maxX = ""
                    maxY = ""
                pieceUrl = str(infoData.find("a")["href"])
                pieceInfo = infoData.find("h3",class_="product-title").text.strip()
                title = pieceInfo.split("(")[0].strip()
                if len(pieceInfo.split("(")) == 1:
                    birth = ""
                elif len(pieceInfo.split("(")) == 2:
                    birth = pieceInfo.split("(")[1].split(")")[0].strip()
                elif len(pieceInfo.split("(")) == 3:
                    birth = pieceInfo.split("(")[2].split(")")[0].strip()
                try:
                    int(birth)
                except:
                    birth = ""
                if title == "":
                    title = "("+pieceInfo.split("(")[1].split("(")[0].strip()
                df_info = pd.DataFrame.from_dict([{
                    "페이지":i-1,
                    "ID":idData,
                    "작가명":key,
                    "작품명":title,
                    "작품명풀네임":pieceInfo,
                    "국가":country,
                    "국적및생몰년도":country_years,
                    "장르":category,
                    "작품년도":birth,
                    "Px-가로":standardX,
                    "Px-세로":standardY,
                    "MaxPx-가로":maxX,
                    "MaxPx-세로":maxY,
                    "url":pieceUrl,
                    "skdata":imgInfo,
                    "이미지 명": "",
                    "이미지 명 생략여부": "",
                    "이미지 저장여부": ""
                }])
                print({
                    "페이지":i-1,
                    "ID":idData,
                    "작가명":key,
                    "작품명":title,
                    "작품명풀네임":pieceInfo,
                    "국가":country,
                    "국적및생몰년도":country_years,
                    "장르":category,
                    "작품년도":birth,
                    "Px-가로":standardX,
                    "Px-세로":standardY,
                    "MaxPx-가로":maxX,
                    "MaxPx-세로":maxY,
                    "url":pieceUrl,
                    "skdata":imgInfo
                })
                df = pd.concat([df,df_info])
                totalCount+=1

        # 최종 작가별 수량 DataFrame 생성
        # 작가명 없음이 있는 경우 처리
        rows = []

        for name, count in artist_count_dict.items():
            if name != "작가명 없음":
                rows.append({"작가명": name, "수량": count})

        # 마지막에 "작가명 없음" 추가
        if "작가명 없음" in artist_count_dict:
            rows.append({"작가명": "작가명 없음", "수량": artist_count_dict["작가명 없음"]})

        df_data = pd.DataFrame(rows)


        return [df,df_data,totalImageInfoList]

    def extractArtistExcelInfo(self,df:pd.DataFrame,df_data:pd.DataFrame,artistUrl:str,artistcount:str,page:int,artistTotalCount:int) -> list[pd.DataFrame]:
        i = 1
        totalCount = 1
        totalImageInfoList:list[dict] = []

        artistName = ""
        country = ""
        artistDescription = ""
        total = ""

        while 1:
            url = f"{artistUrl}page/{i}?&per_page=70"

            try:
                # 쿠키 유지(sess)로 요청 (requests.get -> self.sess.get)
                res = self.sess.get(url, headers=self.headers, timeout=30)
            except Exception as e:
                print(f"요청 예외 발생 : {url}")
                print(f"예외타입 : {type(e).__name__}")
                print(f"예외내용 : {e}")
                traceback.print_exc()
                time.sleep(10)
                i += 1
                continue

            if res.status_code != 200:
                print(f"작가 페이지 응답코드 비정상 : {url}")
                print(f"status_code : {res.status_code}")
                print(f"response_url : {res.url}")
                try:
                    print(f"response_text 앞부분 : {res.text[:500]}")
                except Exception as e:
                    print(f"response_text 출력 실패 : {e}")
                break

            time.sleep(random.uniform(0.45, 0.55))
            soup = BeautifulSoup(res.content,"html.parser")
            if soup.find("div",class_="entry-content") != None or str(soup).find("Sorry, we can't seem to find the page you're looking for") != -1:
                print(f"작가 페이지 없음 또는 비정상 페이지 : {url}")
                break
            i += 1

            # NoneType 방어 (특정 작가 페이지에서 요소 누락되는 케이스)
            artistName = safe_find_text(soup, "h1", class_="entry-title", default="작가명 없음")

            abdate_txt = safe_find_text(soup, "div", class_="abdate", default="")
            if abdate_txt:
                abdate = abdate_txt.strip().split(",")
                country = abdate[0].strip() if len(abdate) > 0 else ""
            else:
                country = ""

            artistDescription = safe_find_text(soup, "div", class_="term-description", default="")

            infoList = soup.find_all("div",class_="pbm")

            total_txt = safe_find_text(soup, "p", class_="woocommerce-result-count", default="")
            total = total_txt.replace("items","").strip() if total_txt else ""

            # === 신규 === 리스트 자체가 비었으면(차단/구조 변경/비정상) 다음 페이지로 넘김
            if not infoList:
                print(f"infoList 없음(차단/구조변경 가능) : {url}")
                continue

            for infoData in infoList:
                # === 신규 === woodmart-product-cats 없을 수 있음
                field = safe_text(infoData.find("div",class_="woodmart-product-cats"), default="").strip()

                data = infoData.find("div")
                # === 신규 === data-id / data-sk 누락 방어
                if data is None or data.get("data-id") is None or data.get("data-sk") is None:
                    print(f"data-id 또는 data-sk 누락 : {url}")
                    continue

                idData = data["data-id"].strip()

                # === 신규 === JSON 파싱 실패 방어
                try:
                    sizeData = json.loads(data["data-sk"])
                except:
                    print(f"data-sk JSON 파싱 실패 : {url} / id={idData}")
                    continue

                imgInfo = sizeData.get("sk", "")

                try:
                    standard = sizeData["sdlimagesize"].split("px")[0].split("x")
                    standardX = standard[0].strip()
                    standardY = standard[1].strip()
                except:
                    standardX = "정보없음"
                    standardY = "정보없음"
                try:
                    max = sizeData["hdlimagesize"].split("px")[0].split("x")
                    maxX = max[0].strip()
                    maxY = max[1].strip()
                except:
                    maxX = "정보없음"
                    maxY = "정보없음"

                # === 신규 === a 태그 누락 방어
                a_tag = infoData.find("a")
                pieceUrl = str(a_tag["href"]) if a_tag and a_tag.get("href") else ""

                pieceInfo = safe_text(infoData.find("h3",class_="product-title"), default="").strip()
                if pieceInfo == "":
                    # === 신규 === 제목 없으면 스킵
                    continue

                title = pieceInfo.split("(")[0].strip()
                if len(pieceInfo.split("(")) == 1:
                    birth = "없음"
                elif len(pieceInfo.split("(")) == 2:
                    birth = pieceInfo.split("(")[1].split(")")[0].strip()
                elif len(pieceInfo.split("(")) == 3:
                    birth = pieceInfo.split("(")[2].split(")")[0].strip()
                try:
                    int(birth)
                except:
                    birth = "없음"
                if title == "":
                    title = "("+pieceInfo.split("(")[1].split("(")[0].strip()

                df_info = pd.DataFrame.from_dict([{
                    "페이지":page,
                    "작가순서":artistTotalCount,
                    "그림순서":totalCount,
                    "ID":idData,
                    "작가명":artistName,
                    "작품명":title,
                    "작품명풀네임":pieceInfo,
                    "국가":country,
                    "장르":field,
                    "작품년도":birth,
                    "수량":total,
                    "Px-가로":standardX,
                    "Px-세로":standardY,
                    "MaxPx-가로":maxX,
                    "MaxPx-세로":maxY,
                    "url":pieceUrl,
                    "skdata":imgInfo
                }])
                df = pd.concat([df,df_info])
                totalCount+=1

        df_data_info =pd.DataFrame.from_dict([{
            "페이지":page,
            "작가명":artistName,
            "국가":country,
            "수량":total,
            "작가내용":artistDescription
        }])
        df_data = pd.concat([df_data,df_data_info])
        return [df,df_data,totalImageInfoList]




def main()->None:
    currentPath = os.getcwd().replace("\\","/")
    excelCheck = input("전체 엑셀 추출 하시겠습니까? 1.예 2. 아니오 : ").strip()
    downloadCheck = input("1. 이미지 다운로드 / 2. 다운안된 이미지 재 다운로드 : ")

    startPage = ""
    selectArtistName = ""

    if downloadCheck == "1":
        startPage = input("추출 페이지를 입력해주세요 (엔터시 처음부터): ").strip()
        selectArtistName:str = input("추출 작가명을 입력해주세요 (엔터시 처음부터): ").strip()
    firstSheetColumn = ["페이지","작가순서","그림순서","ID","작가명","작품명","작품명풀네임","국가","장르","작품년도","수량","Px-가로","Px-세로","MaxPx-가로","MaxPx-세로","url","skdata","이미지 저장여부"]
    secondSheetColumn = ["","페이지","작가명","국가","수량","작가내용"]
    totalImageInfoList:list[dict] = []
    excelIndex = 1
    artvee = ARTVEE()
    headers=artvee.login()
    if excelCheck == "1":
        print("전체 예술가 목록 확인중 ..... ")
        artistUrlList:list[dict] = artvee.getArtistsUrlList()
        print("전체 예술가 목록 확인 완료!")
        print("예술가 정보 엑셀 추출 시작!")
        df = pd.DataFrame(columns=firstSheetColumn)
        df_data = pd.DataFrame(columns=secondSheetColumn)
        beforePage = 1
        for artistInfoForExcel in tqdm(artistUrlList):
            artistUrl=artistInfoForExcel["artistUrl"]
            artistcount=artistInfoForExcel["artistcount"]
            artistPage = artistInfoForExcel["page"]
            artistTotalCount = artistInfoForExcel["totalCount"]
            ################################################
            # url = f"{artistUrl}"
            # res = requests.get(url)
            # soup = BeautifulSoup(res.content,"html.parser")
            # try:
            #     imgUrl = soup.find("img",class_="imspanc")["src"]
            # except:
            #     print(url)
            #     beforePage+=1
            #     continue
            # imgName = soup.find("h1",class_="entry-title").text.strip()
            # number = f"0000{beforePage}"
            # imgName = number[-4:]+" "+imgName
            # imageInfo = requests.get(imgUrl)
            # f = open(f"./result/image/{imgName}.jpg",'wb')
            # f.write(imageInfo.content)
            # f.close()
            # beforePage+=1
            ####################################################
            if len(df["작품명"].tolist()) > 15000 and artistPage != beforePage:
                with pd.ExcelWriter(f"{currentPath}/result/excel/artvee_{excelIndex}.xlsx",engine='openpyxl') as writer: #xlsxwriter
                    df.to_excel(writer,sheet_name="1",index=False)
                    df_data.to_excel(writer,sheet_name="2",index=False)
                excelIndex += 1
                df = pd.DataFrame(columns=firstSheetColumn)
                df_data = pd.DataFrame(columns=secondSheetColumn)
            df_info = artvee.extractArtistExcelInfo(df=df,df_data=df_data,artistUrl=artistUrl,artistcount=artistcount,page=artistPage,artistTotalCount=artistTotalCount)
            df = df_info[0].reset_index(drop=True)
            df_data = df_info[1].reset_index(drop=True)
            totalImageInfoList+=df_info[2]
            beforePage = artistPage
        if len(df["작품명"].tolist()) != 0:
            with pd.ExcelWriter(f"{currentPath}/result/excel/artvee_{excelIndex}.xlsx",engine='openpyxl') as writer:
                df.to_excel(writer,sheet_name="1",index=False)
                df_data.to_excel(writer,sheet_name="2",index=False)
        print("전체 엑셀 추출 완료")
    excelPath = f"{currentPath}/result/excel"
    imagePath = f"{currentPath}/result/image"
    fileList = os.listdir(path=excelPath)

    for fileInfo in fileList:
        if fileInfo.find("~$") != -1:
            print("엑셀파일을 닫아주세요")
            continue
        try:
            df_excel = pd.read_excel(f"{excelPath}/{fileInfo}",sheet_name="1")
            df_excel_data = pd.read_excel(f"{excelPath}/{fileInfo}",sheet_name="2")
        except:
            print(f"{excelPath}/{fileInfo}는 엑셀 파일이 아닙니다.")
            continue
        print(f"{fileInfo} 이미지 추출중")
        for idx, dataInfo in enumerate(tqdm(df_excel["skdata"])):
            imageUrl = f"https://mdl.artvee.com/sdl/{dataInfo}sdl.jpg"
            pageInfo = str(df_excel.at[idx,"페이지"])
            nameInfo = df_excel.at[idx,"작가명"]
            pieceInfo = df_excel.at[idx,"작품명"]
            artistNum = "0000"+str(df_excel.at[idx,"작가순서"])
            artistNum = artistNum[-3:]
            pieceNumInfo = "0000"+str(df_excel.at[idx,"그림순서"])
            pieceNumInfo = pieceNumInfo[-4:]
            idInfo = df_excel.at[idx,"ID"]
            imageIs = df_excel.at[idx,"이미지 저장여부"]
            if downloadCheck =="2" and imageIs != "X":
                continue

            if selectArtistName != "" and selectArtistName != nameInfo:
                continue
            if startPage != "" and startPage != pageInfo:
                continue

            # 번호 제거 2026-03-11
            # filename = f"{pageInfo}_{artistNum}_{pieceNumInfo}_{nameInfo}_{pieceInfo}_{idInfo}"
            filename = f"{nameInfo}_{pieceInfo}_{idInfo}"
            try:
                imageInfo = requests.get(imageUrl,headers=headers,timeout=30)
            except: # timeout으로 인한 넘김
                print(f"{filename} 저장 실패")
                df_excel.at[idx,"이미지 저장여부"] = "X"
                time.sleep(5)
                continue
            if imageInfo.status_code == 200:
                # namePath = f"{imagePath}/{pageInfo}_{nameInfo}"
                namePath = f"{imagePath}/{nameInfo}"
                if os.path.exists(namePath) == False:
                    os.makedirs(namePath)
                try:
                    f = open(f"{namePath}/{filename}.jpg",'wb')
                    f.write(imageInfo.content)
                    f.close()
                    df_excel.at[idx,"이미지 저장여부"] = ""
                except:
                    print(f"{filename} 저장 실패")
                    df_excel.at[idx,"이미지 저장여부"] = "X"
                    time.sleep(5)
            elif imageInfo.status_code == 404:
                soup = BeautifulSoup(imageInfo.content,"xml")
                errormsg = soup.find("Code").text
                if errormsg.find("NoSuchKey") != -1:
                    df_excel.at[idx,"이미지 저장여부"] = "X"
                    continue
            else:
                print(f"{filename} 저장 실패")
                df_excel.at[idx,"이미지 저장여부"] = "X"
                time.sleep(5)
            time.sleep(0.5)
        with pd.ExcelWriter(f"{excelPath}/{fileInfo}",engine='openpyxl') as writer: #xlsxwriter
            df_excel.to_excel(writer,sheet_name="1",index=False)
            df_excel_data.to_excel(writer,sheet_name="2",index=False)

def translatorFromExcel()->None:
    currentPath = os.getcwd().replace("\\","/")

    os.makedirs(f"{currentPath}/result/excel", exist_ok=True)
    os.makedirs(f"{currentPath}/result/image", exist_ok=True)

    excelPath = f"{currentPath}/result/excel"
    fileList = os.listdir(path=excelPath)
    translator = GoogleTranslator(source='auto', target='ko')
    for fileInfo in fileList:
        if fileInfo.find("~$") != -1:
            print("엑셀파일을 닫아주세요")
            continue
        try:
            df_excel = pd.read_excel(f"{excelPath}/{fileInfo}",sheet_name="1")
            df_excel_data = pd.read_excel(f"{excelPath}/{fileInfo}",sheet_name="2")
        except:
            traceback.print_exc()
            print(f"{fileInfo} 엑셀 읽기 실패")
            continue
        for idx, data in enumerate(tqdm(df_excel["페이지"])):
            try:
                pieceInfo = df_excel.at[idx,"작품명"]
                pieceFullInfo = df_excel.at[idx,"작품명풀네임"]
                try:
                    pieceInfoTrans = translator.translate(pieceInfo)
                    pieceFullInfoTrans = translator.translate(pieceFullInfo)
                except:
                    try:
                        time.sleep(20)
                        pieceInfoTrans = translator.translate(pieceInfo)
                        pieceFullInfoTrans = translator.translate(pieceFullInfo)
                    except:
                        time.sleep(60)
                        pieceInfoTrans = translator.translate(pieceInfo)
                        pieceFullInfoTrans = translator.translate(pieceFullInfo)
                if idx !=0 and idx%1000==0:
                    with pd.ExcelWriter(f"{excelPath}/{fileInfo}",engine='openpyxl') as writer: #xlsxwriter
                        df_excel.to_excel(writer,sheet_name="1",index=False)
                        df_excel_data.to_excel(writer,sheet_name="2",index=False)
                time.sleep(0.3)
                df_excel.at[idx,"번역-1(괄호포함)"] = pieceFullInfoTrans
                df_excel.at[idx,"번역-2(괄호 미포함)"] = pieceInfoTrans
            except:
                traceback.print_exc()
                print("페이지 번역 또는 저장 실패")
                df_excel.at[idx,"번역-1(괄호포함)"] = "번역실패"
                df_excel.at[idx,"번역-2(괄호 미포함)"] = "번역실패"
                time.sleep(30)
        with pd.ExcelWriter(f"{excelPath}/{fileInfo}",engine='openpyxl') as writer: #xlsxwriter
            df_excel.to_excel(writer,sheet_name="1",index=False)
            df_excel_data.to_excel(writer,sheet_name="2",index=False)


def sub_main()->None:
    currentPath = os.getcwd()  # 현재 작업 디렉터리
    excelPath = f"{currentPath}/result"
    file_path = os.path.join(excelPath, "artvee_artist_list.xlsx")
    if not os.path.exists(file_path):
        print("artvee_artist_list.xlsx 파일이 존재하지 않습니다.")
        return None
    # 파일이 존재하면 아래 작업을 진행
    print("artvee_artist_list.xlsx 파일이 존재합니다.")
    currentPath = os.getcwd().replace("\\","/")
    excelCheck = input("전체 엑셀 추출 하시겠습니까? 1.예 2. 아니오 : ").strip()
    downloadCheck = input("1. 이미지 다운로드 / 2. 다운안된 이미지 재 다운로드 : ")
    firstSheetColumn = ["페이지","작가순서","그림순서","ID","작가명","작품명","작품명풀네임","국가","장르","작품년도","수량","Px-가로","Px-세로","MaxPx-가로","MaxPx-세로","url","skdata","이미지 저장여부", "에러내용"]
    secondSheetColumn = ["","페이지","작가명","국가","수량","작가내용"]
    totalImageInfoList:list[dict] = []
    excelIndex = 1
    artvee = ARTVEE()
    headers=artvee.login()
    if excelCheck == "1":
        print("추가 예술가 목록 확인중 ..... ")
        artistUrlList:list[dict] = artvee.getExcelArtistsUrlList(file_path)
        print("추가 예술가 목록 확인 완료!")
        print("예술가 정보 엑셀 추출 시작!")
        df = pd.DataFrame(columns=firstSheetColumn)
        df_data = pd.DataFrame(columns=secondSheetColumn)
        beforePage = 1
        for artistInfoForExcel in tqdm(artistUrlList):
            artistUrl=artistInfoForExcel["artistUrl"]
            artistcount=artistInfoForExcel["artistcount"]
            artistPage = artistInfoForExcel["page"]
            artistTotalCount = artistInfoForExcel["totalCount"]
            ################################################
            # url = f"{artistUrl}"
            # res = requests.get(url)
            # soup = BeautifulSoup(res.content,"html.parser")
            # try:
            #     imgUrl = soup.find("img",class_="imspanc")["src"]
            # except:
            #     print(url)
            #     beforePage+=1
            #     continue
            # imgName = soup.find("h1",class_="entry-title").text.strip()
            # number = f"0000{beforePage}"
            # imgName = number[-4:]+" "+imgName
            # imageInfo = requests.get(imgUrl)
            # f = open(f"./result/image/{imgName}.jpg",'wb')
            # f.write(imageInfo.content)
            # f.close()
            # beforePage+=1
            ####################################################
            if len(df["작품명"].tolist()) > 15000 and artistPage != beforePage:
                with pd.ExcelWriter(f"{currentPath}/result/excel/artvee_artist_{excelIndex}.xlsx",engine='openpyxl') as writer: #xlsxwriter
                    df.to_excel(writer,sheet_name="1",index=False)
                    df_data.to_excel(writer,sheet_name="2",index=False)
                excelIndex += 1
                df = pd.DataFrame(columns=firstSheetColumn)
                df_data = pd.DataFrame(columns=secondSheetColumn)
            df_info = artvee.extractArtistExcelInfo(df=df,df_data=df_data,artistUrl=artistUrl,artistcount=artistcount,page=artistPage,artistTotalCount=artistTotalCount)
            df = df_info[0].reset_index(drop=True)
            df_data = df_info[1].reset_index(drop=True)
            totalImageInfoList+=df_info[2]
            beforePage = artistPage
        if len(df["작품명"].tolist()) != 0:

            with pd.ExcelWriter(f"{currentPath}/result/excel/artvee_artist_{excelIndex}.xlsx",engine='openpyxl') as writer: #xlsxwriter
                df.to_excel(writer,sheet_name="1",index=False)
                df_data.to_excel(writer,sheet_name="2",index=False)
        print("전체 엑셀 추출 완료")
    excelPath = f"{currentPath}/result/excel"
    imagePath = f"{currentPath}/result/image"
    fileList = os.listdir(path=excelPath)

    for fileInfo in fileList:
        if fileInfo.find("~$") != -1:
            print("엑셀파일을 닫아주세요")
            continue
        try:
            df_excel = pd.read_excel(f"{excelPath}/{fileInfo}",sheet_name="1")
            df_excel_data = pd.read_excel(f"{excelPath}/{fileInfo}",sheet_name="2")
        except:
            print(f"{excelPath}/{fileInfo}는 엑셀 파일이 아닙니다.")
            continue
        print(f"{fileInfo} 이미지 추출중")
        for idx, dataInfo in enumerate(tqdm(df_excel["skdata"])):
            imageUrl = f"https://mdl.artvee.com/sdl/{dataInfo}sdl.jpg"
            pageInfo = str(df_excel.at[idx,"페이지"])
            nameInfo = df_excel.at[idx,"작가명"]
            pieceInfo = df_excel.at[idx,"작품명"]
            artistNum = "0000"+str(df_excel.at[idx,"작가순서"])
            artistNum = artistNum[-3:]
            pieceNumInfo = "0000"+str(df_excel.at[idx,"그림순서"])
            pieceNumInfo = pieceNumInfo[-4:]
            idInfo = df_excel.at[idx,"ID"]
            imageIs = df_excel.at[idx,"이미지 저장여부"]
            if downloadCheck =="2" and imageIs != "X":
                continue
            # filename = f"{pageInfo}_{artistNum}_{pieceNumInfo}_{nameInfo}_{pieceInfo}_{idInfo}"
            filename = f"{nameInfo}_{pieceInfo}_{idInfo}"
            try:
                imageInfo = requests.get(imageUrl,headers=headers,timeout=30)
            except: # timeout으로 인한 넘김
                print(f"{filename} 저장 실패")
                df_excel.at[idx,"이미지 저장여부"] = "X"
                time.sleep(5)
                continue
            if imageInfo.status_code == 200:
                # namePath = f"{imagePath}/{pageInfo}_{nameInfo}"
                namePath = f"{imagePath}/{nameInfo}"
                if os.path.exists(namePath) == False:
                    os.makedirs(namePath)
                try:
                    f = open(f"{namePath}/{filename}.jpg",'wb')
                    f.write(imageInfo.content)
                    f.close()
                    df_excel.at[idx,"이미지 저장여부"] = ""
                except:
                    print(f"{filename} 저장 실패")
                    df_excel.at[idx,"이미지 저장여부"] = "X"
                    time.sleep(5)
            elif imageInfo.status_code == 404:
                soup = BeautifulSoup(imageInfo.content,"xml")
                errormsg = soup.find("Code").text
                if errormsg.find("NoSuchKey") != -1:
                    df_excel.at[idx,"이미지 저장여부"] = "없음"
                    continue
            else:
                print(f"{filename} 저장 실패")
                df_excel.at[idx,"이미지 저장여부"] = "X"
                time.sleep(5)
            time.sleep(0.5)
        with pd.ExcelWriter(f"{excelPath}/{fileInfo}",engine='openpyxl') as writer: #xlsxwriter
            df_excel.to_excel(writer,sheet_name="1",index=False)
            df_excel_data.to_excel(writer,sheet_name="2",index=False)


def collection_filter()-> tuple[str, str]:
    excelCheck = input("전체 엑셀 추출 하시겠습니까? 1.예 2. 아니오 : ").strip()
    downloadCheck = input("1. 이미지 다운로드 / 2. 다운안된 이미지 재 다운로드 : ")
    return excelCheck, downloadCheck


def collection_main(category, excelCheck, downloadCheck) -> None:
    currentPath = os.getcwd().replace("\\", "/")
    excelPath = f"{currentPath}/result/excel/collection"
    os.makedirs(excelPath, exist_ok=True)

    file_path = os.path.join(excelPath, f"artvee_{category}.xlsx")
    firstSheetColumn = ["페이지", "ID", "작가명", "작품명", "작품명풀네임", "국가", "국적및생몰년도", "장르", "작품년도",
                        "Px-가로", "Px-세로", "MaxPx-가로", "MaxPx-세로", "url", "skdata", "이미지 명", "이미지 명 생략여부", "이미지 저장여부", "에러내용"]
    secondSheetColumn = ["작가명", "수량"]

    # 파일이 없으면 생성
    if not os.path.exists(file_path):
        print(f"✅ artvee_{category}.xlsx 파일이 존재하지 않아 새로 생성합니다.")
        df1 = pd.DataFrame(columns=firstSheetColumn)
        df2 = pd.DataFrame(columns=secondSheetColumn)
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df1.to_excel(writer, sheet_name="1", index=False)
            df2.to_excel(writer, sheet_name="2", index=False)
    else:
        print(f"📂 artvee_{category}.xlsx 파일이 존재합니다.")

    # 엑셀 로딩 후 작업 진행
    totalImageInfoList: list[dict] = []
    artvee = ARTVEE()
    headers = artvee.login()

    collectionUrl = f"https://artvee.com/c/{category}/"
    collectionCount = "0"

    if excelCheck == "1":
        print(f"{category} 정보 엑셀 추출 시작!")
        df = pd.DataFrame(columns=firstSheetColumn)
        df_data = pd.DataFrame(columns=secondSheetColumn)
        df_info = artvee.extractCollectionExcelInfo(df=df,df_data=df_data,collectionUrl=collectionUrl,category=category)
        df = df_info[0].reset_index(drop=True)
        df_data = df_info[1].reset_index(drop=True)
        totalImageInfoList+=df_info[2]
        if len(df["작품명"].tolist()) != 0:
            with pd.ExcelWriter(f"{currentPath}/result/excel/collection/artvee_{category}.xlsx",engine='openpyxl') as writer: #xlsxwriter
                df.to_excel(writer,sheet_name="1",index=False)
                df_data.to_excel(writer,sheet_name="2",index=False)
            print("전체 엑셀 추출 완료")

    file_name = f"artvee_{category}.xlsx"
    excelPath = f"{currentPath}/result/excel/collection"
    imageCategoryPath = f"{currentPath}/result/image/collection/{category}/category"
    imageArtistPath = f"{currentPath}/result/image/collection/{category}/artist"
    file_path = os.path.join(excelPath, file_name)

    if not os.path.exists(file_path):
        print(f"{file_name} 파일이 존재하지 않습니다.")
        return

    fileInfo = file_name  # for문 없이 변수만 지정

    if fileInfo.find("~$") != -1:
        print("엑셀파일을 닫아주세요")
        return
    try:
        df_excel = pd.read_excel(f"{excelPath}/{fileInfo}",sheet_name="1")
        df_excel_data = pd.read_excel(f"{excelPath}/{fileInfo}",sheet_name="2")
    except:
        print(f"{excelPath}/{fileInfo}는 엑셀 파일이 아닙니다.")
        return
    print(f"{fileInfo} 이미지 추출중")


    MAX_PATH_LENGTH = 260  # Windows 제한
    ext = ".jpg"

    # 🔧 경고 방지: 문자열 타입 명시
    df_excel["이미지 명"] = df_excel["이미지 명"].astype(str)
    df_excel["이미지 명 생략여부"] = df_excel["이미지 명 생략여부"].astype(str)
    df_excel["이미지 저장여부"] = df_excel["이미지 저장여부"].astype(str)
    df_excel["에러내용"] = df_excel["에러내용"].astype(str)

    # 메인 다운로드 루프

    total_records = len(df_excel["skdata"])
    print(f"🔢 총 레코드 수: {total_records}")

    for idx, dataInfo in enumerate(tqdm(df_excel["skdata"], desc="이미지 저장 중", total=total_records)):
        imageUrl = f"https://mdl.artvee.com/sdl/{dataInfo}sdl.jpg"
        nameInfo = df_excel.at[idx, "작가명"]
        pieceInfo = df_excel.at[idx, "작품명"]
        idInfo = df_excel.at[idx, "ID"]
        imageIs = df_excel.at[idx, "이미지 저장여부"]

        if downloadCheck == "2" and imageIs != "X":
            print(f"⏭️ 다운로드 스킵됨 - idx: {idx}, ID: {idInfo}, 저장여부: {imageIs}")
            # 🔧 NaN 값 공백으로 처리 (3개 컬럼)
            for col in ["이미지 저장여부", "이미지 명 생략여부", "에러내용"]:
                val = df_excel.at[idx, col]
                if pd.isna(val) or str(val).strip().lower() == "nan":
                    df_excel.at[idx, col] = ""
            continue

        original_filename = f"{nameInfo}_{pieceInfo}_{idInfo}"
        safe_filename = sanitize_filename(original_filename)

        df_excel.at[idx, "이미지 저장여부"] = "O"
        df_excel.at[idx, "이미지 명"] = ""
        df_excel.at[idx, "이미지 명 생략여부"] = ""
        df_excel.at[idx, "에러내용"] = ""

        try:
            imageInfo = requests.get(imageUrl, headers=headers, timeout=30)
        except Exception as e:
            print(f'e :{e}')
            print(f"{safe_filename} 저장 실패")
            df_excel.at[idx, "이미지 저장여부"] = "X"
            df_excel.at[idx, "이미지 명"] = ""
            df_excel.at[idx, "이미지 명 생략여부"] = ""
            df_excel.at[idx, "에러내용"] = f"{e}"
            time.sleep(5)
            continue

        if imageInfo.status_code == 200:
            try:
                # ✅ (1) category 저장
                os.makedirs(imageCategoryPath, exist_ok=True)
                filename_category, omitted_cat = shorten_filename(Path(imageCategoryPath), safe_filename)
                with open(Path(imageCategoryPath) / f"{filename_category}{ext}", 'wb') as f:
                    f.write(imageInfo.content)

                # ✅ (2) 작가별 폴더 저장
                safe_artist_name = sanitize_filename(nameInfo)
                artist_dir = Path(imageArtistPath) / safe_artist_name
                artist_dir.mkdir(parents=True, exist_ok=True)

                filename_artist, omitted_art = shorten_filename(artist_dir, safe_filename)
                image_path = artist_dir / f"{filename_artist}{ext}"
                with open(image_path, 'wb') as f:
                    f.write(imageInfo.content)

                print(f"{idx + 1} : {filename_artist}{ext} 이미지 업로드 성공")

                # ✅ 엑셀 업데이트
                df_excel.at[idx, "이미지 명"] = f"{filename_artist}{ext}"
                df_excel.at[idx, "이미지 명 생략여부"] = "O" if "O" in [omitted_cat, omitted_art] else ""
                df_excel.at[idx, "이미지 저장여부"] = "O"
                df_excel.at[idx, "에러내용"] = ""

            except Exception as e:
                print(f'e :{e}')
                print(f"{safe_filename} 저장 실패")
                df_excel.at[idx, "이미지 저장여부"] = "X"
                df_excel.at[idx, "이미지 명"] = ""
                df_excel.at[idx, "이미지 명 생략여부"] = ""
                df_excel.at[idx, "에러내용"] = f"{e}"
                time.sleep(5)

        elif imageInfo.status_code == 404:
            try:
                soup = BeautifulSoup(imageInfo.content, "xml")
                errormsg = soup.find("Code").text
                print(f"{safe_filename} {errormsg} 저장 실패")
                if "NoSuchKey" in errormsg:
                    df_excel.at[idx, "이미지 저장여부"] = "X"
                    df_excel.at[idx, "이미지 명"] = ""
                    df_excel.at[idx, "이미지 명 생략여부"] = ""
                    df_excel.at[idx, "에러내용"] = "Download 확인 NoSuchKey"
            except Exception as e:
                df_excel.at[idx, "이미지 저장여부"] = "X"
                df_excel.at[idx, "이미지 명"] = ""
                df_excel.at[idx, "이미지 명 생략여부"] = ""
                df_excel.at[idx, "에러내용"] = "404 처리중 에러"
        else:
            print(f"{safe_filename} 저장 실패")
            df_excel.at[idx, "이미지 저장여부"] = "X"
            df_excel.at[idx, "이미지 명"] = ""
            df_excel.at[idx, "이미지 명 생략여부"] = ""
            df_excel.at[idx, "에러내용"] = "기타에러"
            time.sleep(5)

        time.sleep(0.5)

    # ✅ 엑셀 저장
    with pd.ExcelWriter(f"{excelPath}/{fileInfo}", engine='openpyxl') as writer:
        df_excel.to_excel(writer, sheet_name="1", index=False)
        df_excel_data.to_excel(writer, sheet_name="2", index=False)


# 🔧 파일명 안전화 함수
def sanitize_filename(filename: str) -> str:
    filename = filename.replace("/", "_").replace("\\", "_")
    filename = re.sub(r'[<>:"|?*\u2018\u2019\u201C\u201D]', '', filename)  # ‘’, “”, 특수 따옴표 제거
    return filename.strip()


# 🔧 경로에 맞춰 파일명 자르기 함수
def shorten_filename(base_path: Path, filename: str) -> (str, str):
    MAX_PATH_LENGTH = 250  # Windows 제한
    ext = ".jpg"
    safe_name = sanitize_filename(filename)
    max_len = MAX_PATH_LENGTH - len(str(base_path.resolve())) - 1 - len(ext)
    if len(safe_name) > max_len:
        return safe_name[:max_len], "O"
    return safe_name, "X"


def count_images_in_folder(folder_path):
    """주어진 폴더에서 .jpg 파일의 개수를 셈"""
    image_count = 0
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(".jpg"):
                image_count += 1
    return image_count


if __name__ == "__main__":
    init_logger()  # 로그 초기화
    mode = input("1. artvee 다운 / 2. 엑셀 번역 : / 3. artvee artist 다운 : / 4. collection by category 선택 : / 5. 이미지 수 확인" )
    if mode == "1":
        try:
            main()
        except Exception as e:
            print(f"{str(e)} 오류로 인한 종료")
            traceback.print_exc()
    elif mode == "2":
        try:
            translatorFromExcel()
        except Exception as e:
            print(f"{str(e)} 오류로 인한 종료")
            traceback.print_exc()
    elif mode == "3":
        try:
            sub_main()
        except Exception as e:
            print(f"{str(e)} 오류로 인한 종료")
            traceback.print_exc()
    elif mode == "4":
        print("\n")
        print("-------------------------------------------------------------------------------------")
        print("\n")
        print("1. Abstract / 2. Figurative / 3. Landscape / 4. Posters / 5. Illustration")
        print("6. Religion / 7. Drawings / 8. Mythology / 9. Botanical / 10. Asian Art / 11. Animals")

        selected = input("다운받을 카테고리 번호를 입력하세요 (예: 1,3,5): ")

        # 번호와 카테고리 매핑
        category_map = {
            1: "abstract",
            2: "figurative",
            3: "landscape",
            4: "posters",
            5: "illustration",
            6: "religion",
            7: "drawings",
            8: "mythology",
            9: "botanical",
            10: "asian-art",
            11: "animals"
        }

        try:
            category_numbers = [int(num.strip()) for num in selected.split(",") if num.strip().isdigit()]
            selected_categories = [category_map[num] for num in category_numbers if num in category_map]
            print(f"선택된 카테고리 이름: {selected_categories}")

            # 선택된 카테고리 이름 리스트를 collection_main에 넘김

            excelCheck, downloadCheck = collection_filter()

            for category in selected_categories:
                collection_main(category, excelCheck, downloadCheck)

        except Exception as e:
            print(f"{str(e)} 오류로 인한 종료")
            traceback.print_exc()

    elif mode == "5":
        # 카테고리 번호와 카테고리 매핑
        category_map = {
            1: "abstract",
            2: "figurative",
            3: "landscape",
            4: "posters",
            5: "illustration",
            6: "religion",
            7: "drawings",
            8: "mythology",
            9: "botanical",
            10: "asian-art",
            11: "animals"
        }

        # 카테고리 번호 입력 받기
        print("\n")
        print("-------------------------------------------------------------------------------------")
        print("\n")
        print("1. Abstract / 2. Figurative / 3. Landscape / 4. Posters / 5. Illustration")
        print("6. Religion / 7. Drawings / 8. Mythology / 9. Botanical / 10. Asian Art / 11. Animals")
        selected = input("이미지수를 확인할 카테고리 번호를 입력하세요 (예: 1,3,5): ")

        selected_categories = [int(num.strip()) for num in selected.split(",")]

        for category_num in selected_categories:
            if category_num not in category_map:
                print(f"잘못된 번호입니다: {category_num}")
                continue

            category_name = category_map[category_num]
            category_path = os.path.join("result", "image", "collection", category_name, "category")

            # category 폴더 내 이미지 수
            category_image_count = count_images_in_folder(category_path)
            print(f"{category_name} 카테고리 'category' 폴더 내 이미지 수: {category_image_count}개")

            # artist 폴더 내 이미지 수
            artist_folder_path = os.path.join("result", "image", "collection", category_name, "artist")
            artist_image_count = 0
            for artist_folder in os.listdir(artist_folder_path):
                artist_path = os.path.join(artist_folder_path, artist_folder)
                if os.path.isdir(artist_path):
                    artist_image_count += count_images_in_folder(artist_path)

            print(f"{category_name} 카테고리 'artist' 폴더 내 이미지 수: {artist_image_count}개")
            print("-------------------------------------------------------------------------------------")

    input("완료")