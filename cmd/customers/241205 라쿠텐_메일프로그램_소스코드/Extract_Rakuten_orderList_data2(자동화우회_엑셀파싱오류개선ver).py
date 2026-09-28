
# 필요한 라이브러리 임포트
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pyperclip
import time
from bs4 import BeautifulSoup
from datetime import datetime
import xlsxwriter
import requests
import os
import sys
import io
from PIL import Image

# ID/PW 파일 읽기
try:
    file_path = './setting/idpw.txt'
    with open(file_path) as f:
        userid = f.readline().strip()  # 첫 번째 줄은 userid로 저장
        userpw = f.readline().strip()  # 두 번째 줄은 userpw로 저장
except FileNotFoundError:
    print("ID/PW 파일을 찾을 수 없습니다:", file_path)
    sys.exit(1)


# 아래에서 사용하는 리스트
def get_null_list(wod, topss):
    c = [wod]
    null_list = ['' for i in range(topss - 1)]
    c.extend(null_list)
    return c

# 웹 드라이버 옵션 설정
chrome_options = Options()
# chrome_options.add_argument('--headless')  # 백그라운드 실행을 위해 headless 모드로 설정 (디버깅을 위해 비활성화)
chrome_options.add_argument('--disable-gpu')  # GPU 가속 사용 안함
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--disable-software-rasterizer')
chrome_options.add_argument('--enable-unsafe-swiftshader')  # WebGL 관련 경고 해결
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)

# 웹 드라이버 경로 설정 - selenium 업데이트로 따로 드라이버의 경로 지정 하지 않아도 됨
driver = webdriver.Chrome(options=chrome_options)
driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
    'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
})
driver.implicitly_wait(10)

# 네이버 로그인 함수 정의
def naver_login(driver, userid, userpw):
    driver.get('https://nid.naver.com/nidlogin.login')
    
    # 아이디와 비밀번호 입력 (pyperclip을 사용하여 복사-붙여넣기 방식으로 입력)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, 'id')))
    driver.find_element(By.NAME, 'id').click()
    pyperclip.copy(userid)
    driver.find_element(By.NAME, 'id').send_keys(Keys.CONTROL, 'v')
    time.sleep(1)
    
    driver.find_element(By.NAME, 'pw').click()
    pyperclip.copy(userpw)
    driver.find_element(By.NAME, 'pw').send_keys(Keys.CONTROL, 'v')
    time.sleep(1)

    # 로그인 버튼 클릭
    driver.find_element(By.XPATH, '//*[@id="log.login"]').click()
    
    # 기기 등록 '등록안함' 버튼 클릭 시도
    try:
        element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "span.btn_cancel"))
        )
        element.click()
    except:
        print("기기 등록 '등록안함' 버튼을 찾을 수 없습니다.")
    
    # 로그인 확인 로직 추가
    try:
        WebDriverWait(driver, 10).until_not(EC.presence_of_element_located((By.NAME, 'id')))
    except:
        return False
    return True
    
# 로그인 시도 및 재시도 로직 추가
login_attempts = 0
while login_attempts < 3:
    if naver_login(driver, userid, userpw):
        break
    login_attempts += 1
    print(f"로그인 실패. {login_attempts}번째 시도 중입니다.")
    time.sleep(5)
else:
    print("로그인 실패. 아이디와 비밀번호를 확인하세요.")
    sys.exit(1)

# 로그인 완료 후 쿠키 가져오기
cookies = driver.get_cookies()
session = requests.Session()
session.cookies = requests.utils.cookiejar_from_dict({cookie['name']: cookie['value'] for cookie in cookies})

# 메일 페이지로 이동
driver.get('https://mail.naver.com/')

# 로그인 상태 확인
if "로그인" in driver.page_source:
    print("로그인 상태가 아닙니다. 다시 확인해주세요.")
    sys.exit(1)
    
# 메일 내 데이터 파싱 코드
text_list = []
html_list = []
page = 0
sw = True
while sw:
    page+=1
    data = {'folderSN':-1,
    'reQuery':'false',
    'type':'all',
    'from':'',
    'to':'',
    'content':'',
    'body':'【楽天市場】注文内容ご確認',
    'bodyCond':0,
    'page':page,
    'sortField':1,
    'sortType':0,
    'useSearchHistory':'true',
    'u':userid}
    
    text = session.post('https://mail.naver.com/json/search/',data=data).json()['mailData']
    if text == []:
        sw = False
    else:
        print('page : {0}'.format(page))
        text_list.extend(text)
        time.sleep(1)

html_list = []
top = len(text_list)
for i,v in enumerate(text_list):
    num = v['mailSN']
    idt = v['replyTo']['email'].split('@')[0]
    url = 'https://mail.naver.com/json/read/?charset=&prevNextMail=true&threadMail=true&listScrollPosition=0&mailSN={0}&previewMode=2&u={1}'
    text1 = session.post(url.format(num,idt)).json()
    try:
        html_list.append(text1['mailInfo']['body'])
    except:
        pass
    print('data_get top : {0} / count : {1}'.format(top,i+1))
    if i%20 == 0:
        time.sleep(1)

d_index = []  
datast = {'NO':[],'날짜':[],'이미지':[],'결제 수단':[],'주문번호':[],'일어명':[],'   ':[],'    ':[],'가격':[],'개수':[],'총비용':[],'     ':[],'      ':[],'       ':[],'        ':[],'포인트':[],'쿠폰':[],'상점명':[],'src':[],'url':[],'수취인':[]}
tosyt = len(html_list)
for inds,html in enumerate(html_list):
    
    print('data_process top : {0} / count : {1}'.format(tosyt,inds+1))
    img = []
    soup = BeautifulSoup(html, 'html.parser')
    tdata = ''
    swsw = True
    try:
        tdata = soup.select('font[color="#000000"]')[2].get_text().split('\xa0')
    except:
        d_index.append(inds)
        swsw = False
    if swsw:    
        id_code = tdata[1].replace('注文日時','')
        times = tdata[2]
        
        title = soup.select('b')[1].get_text()
        
        st = []
        for i,v in enumerate(soup.select('td > table')):
            try:
                v.select('img')[0]
                for j in v.select('a'):
                    if j['href'].find('https://item.rakuten.co.jp/') != -1:
                        s = v.get_text()
                        if s.find('円') != -1 and s.find('個') != -1:
                            st.append(v)
                            break
            except:
                pass
            
        st = st[1:]
        
        
        indext = []
        pr = []
        for i,v in enumerate(st):
            try:
                pr.append(v.select('td[style="max-width:664px;"]')[0].get_text())
                indext.append(i)
            except:
                try:
                    pr.append(v.select('td[style="max-width: 664px;"]')[0].get_text())  
                    indext.append(i)
                except:
                    pass

        pr1 = [i.split(' ')[0].replace('円','').replace(',','').strip() for i in pr]
        pr2 = [i.split(' ')[2].replace('個','').replace(',','').strip() for i in pr]
        
        
        
        title2 = []
        durl_list = []
        
        
        try:
            title2 = [st[i].select('a[style="text-decoration: none; color:#1d54a7;"]')[0].get_text().strip() for i in indext]
            durl_list = [st[i].select('a[style="text-decoration: none; color:#1d54a7;"]')[0]['href'].split('?scid=me')[0] for i in indext]
        except:
            title2 = [st[i].select('a[style="text-decoration:none;color:#1d54a7"]')[0].get_text().strip() for i in indext]
            durl_list = [st[i].select('a[style="text-decoration:none;color:#1d54a7"]')[0]['href'].split('?scid=me')[0] for i in indext]
        
        

        al_pr = ''
        for i in soup.select('font[color="#bf0000"]'):
            if i.get_text().find('円') != -1:
                al_pr = i.get_text().replace('（円）','').replace('円','').replace(',','').strip()
                break
        point = ''
        cupon = ''
        
        for i in soup.select('tr'):
            try:
                if i.select('td')[0].get_text().find('ポイント利用') != -1:
                    point = i.select('td[align="right"]')[0].get_text()
                    if point[0].find('-') != -1:
                        point = point.replace('（円）','').replace('円','').replace(',','').replace('-','').strip()
                        break
                    else:
                        point = ''
            except:
                pass
        for i in soup.select('tr'):
            try:
                if i.select('td')[0].get_text().find('クーポン利用') != -1:
                    cupon = i.select('td[align="right"]')[0].get_text()
                    if cupon[0].find('-') != -1:
                        cupon = cupon.replace('（円）','').replace('円','').replace(',','').replace('-','').strip()
                        break
                    else:
                        cupon = ''                
            except:
                pass
        img = [st[i].select('img')[0]['src'] for i in indext]
        
        scin = ''
        try:
            tr_list = [i.get_text().strip() for i in soup.select('tr')]
            scin = tr_list[tr_list.index('送付先')+1] 
        except:
            try:
                scin = tr_list[tr_list.index('お届け先')+1] 
            except:
                pass
            
        gursu = ''
        try:
            tr_list = [i.get_text().strip() for i in soup.select('tr')]
            gursu = soup.select('tr')[tr_list.index('お支払い方法')+1].find('tr').find('tr').text
        except:
            pass            
            
            
        
        tops = len(title2)
        datast['결제 수단'].extend([gursu for i in range(tops)])
        datast['가격'].extend(pr1)
        datast['개수'].extend(pr2)
        datast['일어명'].extend(title2)      
        datast['상점명'].extend([title for i in range(tops)])
        datast['src'].extend(img)
        datast['url'].extend(durl_list) 
        datast['날짜'].extend(get_null_list(times,tops))
        datast['주문번호'].extend(get_null_list(id_code,tops))
        datast['총비용'].extend(get_null_list(al_pr,tops))
        datast['포인트'].extend(get_null_list(point,tops))
        
        datast['수취인'].extend([scin for i in range(tops)])
        datast['쿠폰'].extend(get_null_list(cupon,tops))


datast['NO'] = [i+1 for i,v in enumerate(datast['상점명'])]
datast['   '] = ['' for i,v in enumerate(datast['상점명'])]
datast['    '] = ['' for i,v in enumerate(datast['상점명'])]
datast['     '] = ['' for i,v in enumerate(datast['상점명'])]
datast['      '] = ['' for i,v in enumerate(datast['상점명'])]
datast['       '] = ['' for i,v in enumerate(datast['상점명'])]
datast['        '] = ['' for i,v in enumerate(datast['상점명'])]
datast['이미지'] = ['' for i,v in enumerate(datast['상점명'])]

# 이미지 다운로드 및 크기 조정 함수 정의

def download_and_resize_image(url, save_path, size=(30, 30)):
    response = requests.get(url)
    if response.status_code == 200:
        image = Image.open(io.BytesIO(response.content))
        image = image.resize(size, Image.ANTIALIAS)  # 이미지 크기 조정
        image.save(save_path)

# 이미지 다운로드 및 크기 조정
if not os.path.exists('./img'):
    os.makedirs('./img')


top = len(datast['src'])
for i,v in enumerate(datast['src']):
    print('img top : {0} / count : {1}'.format(top,i+1))
    response = requests.get(v)
    if response.status_code == 200:
        try:
            os.mkdir('./img')
        except:
            pass
        with open("./img/{0}.jpg".format(str(i)), 'wb') as f:
            f.write(response.content)

word_list = []
word = ''
for i in datast['일어명']:
    word+=i+'℡'
    if len(word) > 4500:
        word_list.append(word[:-1])
        word=''


now = datetime.now() 
file_name = str(now).replace('-','.').replace(':','.')
print('===============[ 엑셀 저장 중 ]===============')


dak = ['NO', '날짜', '이미지','결제 수단', '주문번호', '일어명', '   ', '    ', '가격', '개수', '총비용', '     ', '      ', '       ', '        ', '포인트', '쿠폰', '상점명', 'src','url','수취인']

file_name = './data({0}).xlsx'.format(file_name)
workbook = xlsxwriter.Workbook(file_name, {'strings_to_urls': False})
worksheet = workbook.add_worksheet()
for i,v in enumerate(dak):
    worksheet.write(0, i, v)
    for i1,v1 in enumerate(datast[v]):
        worksheet.write(i1+1, i, v1)
    
for i,v in enumerate(datast['src']):
    worksheet.insert_image(i+1, 2, './img/{0}.jpg'.format(i), options={'x_scale': 1, 'y_scale': 1})
worksheet.set_default_row(60)
workbook.close()

print('================[ 작업 완료 ]==================')

b = input('작업이 완료 되었습니다. 아무키나 입력하시면 종료합니다.')