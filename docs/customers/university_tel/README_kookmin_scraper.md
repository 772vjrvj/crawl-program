
# Kookmin contact scraper

## 설치
```bash
pip install playwright beautifulsoup4 lxml pandas
playwright install chromium
```

## 실행
```bash
python kookmin_contact_scraper.py --output kookmin_contacts.csv
```

## 옵션
```bash
python kookmin_contact_scraper.py --headless false --max-pages-per-site 60
python kookmin_contact_scraper.py --limit-seeds 3
```

## 출력 컬럼
- top_category: 대학 / 일반대학원 / 전문대학원 / 특수대학원
- seed_unit: 시작한 단위
- page_title
- source_url
- source_domain
- page_type
- unit_hint
- sub_unit_hint
- role_type
- name
- email
- phone
- office
- raw_context

## 메모
- 사이트마다 구조가 달라서 best-effort 방식입니다.
- 어떤 페이지는 이메일이 텍스트가 아니라 아이콘/이미지로만 노출되어 빈칸이 남을 수 있습니다.
- 그 경우에도 source_url, phone, office, context는 남도록 설계했습니다.
