
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kookmin University public-site contact scraper.

What it does
------------
- Starts from the public Kookmin University "대학ㆍ대학원" menu seeds.
- Visits each college / graduate-school site with Playwright (Chromium).
- Collects likely detail pages (교수진, 행정직원, 교직원, staff, faculty, organization, 학부, 학과, 전공, 대학원 ...).
- Extracts plain-text emails, mailto links, and nearby metadata (name / phone / office / role / unit).
- Saves everything to CSV.

Why Playwright?
---------------
Many sites render content dynamically, and some professor/staff cards expose extra fields
only after clicking "프로필 더 보기" or similar UI. Static requests-only scraping misses a lot.

Limitations
-----------
- Some pages expose only an email icon/image without an actual text email in the rendered DOM.
  In those cases this script will keep the row but email may stay blank.
- Site structure differs a lot by subdomain, so this is a best-effort extractor, not a perfect oracle.
- Be polite: don't set concurrency too high.

Usage
-----
pip install playwright beautifulsoup4 lxml pandas
playwright install chromium

python kookmin_contact_scraper.py --output kookmin_contacts.csv
python kookmin_contact_scraper.py --headless false --max-pages-per-site 60
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from collections import deque
from dataclasses import dataclass, asdict
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse, urldefrag

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


MAIN_PORTAL = "https://www.kookmin.ac.kr/user/index.do"

# Top-level seeds from the university "대학ㆍ대학원" menu.
SEEDS: list[dict[str, str]] = [
    {"top_category": "대학", "unit": "글로벌인문∙지역대학", "url": "https://cha.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "사회과학대학", "url": "https://social.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "법과대학", "url": "https://law.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "경상대학", "url": "https://kyungsang.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "공과대학", "url": "https://engineering.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "조형대학", "url": "https://design.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "과학기술대학", "url": "https://cst.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "예술대학", "url": "https://art.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "체육대학", "url": "https://sport.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "경영대학", "url": "https://biz.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "소프트웨어융합대학", "url": "https://cs.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "건축대학", "url": "https://archi.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "자동차모빌리티대학", "url": "https://auto.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "미래융합대학", "url": "https://kmu-cts.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "KMU International Business School", "url": "https://kibs.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "교양대학", "url": "https://culture.kookmin.ac.kr"},
    {"top_category": "대학", "unit": "교직과정부", "url": "https://teaching.kookmin.ac.kr"},
    {"top_category": "일반대학원", "unit": "일반대학원", "url": "https://gds.kookmin.ac.kr"},
    {"top_category": "전문대학원", "unit": "테크노디자인전문대학원", "url": "https://ted.kookmin.ac.kr"},
    {"top_category": "전문대학원", "unit": "자동차모빌리티대학원", "url": "https://gsam.kookmin.ac.kr"},
    {"top_category": "전문대학원", "unit": "비즈니스IT대학원", "url": "https://bit.kookmin.ac.kr"},
    {"top_category": "특수대학원", "unit": "교육대학원", "url": "https://edu.kookmin.ac.kr"},
    {"top_category": "특수대학원", "unit": "경영대학원", "url": "https://mba.kookmin.ac.kr"},
    {"top_category": "특수대학원", "unit": "행정대학원", "url": "https://gspa.kookmin.ac.kr"},
    {"top_category": "특수대학원", "unit": "자동차산업대학원", "url": "https://gsaik.kookmin.ac.kr"},
    {"top_category": "특수대학원", "unit": "디자인대학원", "url": "https://gsd.kookmin.ac.kr"},
    {"top_category": "특수대학원", "unit": "정치대학원", "url": "https://gspl.kookmin.ac.kr"},
    {"top_category": "특수대학원", "unit": "스포츠산업대학원", "url": "https://sports.kookmin.ac.kr"},
    {"top_category": "특수대학원", "unit": "법무대학원", "url": "https://ifl.kookmin.ac.kr"},
    {"top_category": "특수대학원", "unit": "종합예술대학원", "url": "https://totalart.kookmin.ac.kr"},
    {"top_category": "특수대학원", "unit": "글로벌창업벤처대학원", "url": "https://gsge.kookmin.ac.kr"},
    {"top_category": "특수대학원", "unit": "소프트웨어융합대학원", "url": "https://swgs.kookmin.ac.kr"},
    {"top_category": "특수대학원", "unit": "글로벌평화ㆍ통일 대학원", "url": "https://gpu.kookmin.ac.kr"},
    {"top_category": "특수대학원", "unit": "아시아올림픽대학원", "url": "https://ogs.kookmin.ac.kr"},
]

# Link texts / href parts that are useful to follow.
FOLLOW_PATTERNS = [
    "교수진", "교수", "faculty",
    "행정직원", "교직원", "staff", "organization", "조직", "기구",
    "학부", "학과", "전공", "department", "major",
    "대학원", "graduate",
    "소개", "about",
    "연구실", "lab", "랩실",
    "people", "directory", "member",
]

# Pages to avoid.
SKIP_PATTERNS = [
    "공지", "news", "board", "bbs", "article", "notice", "calendar",
    "event", "gallery", "video", "youtube", "facebook", "instagram",
    "blog", "admission", "qna", "faq",
]

EMAIL_RE = re.compile(r'(?i)\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b')
PHONE_RE = re.compile(r'0\d{1,2}-\d{3,4}-\d{4}')
ROLE_RE = re.compile(
    r'(교수|명예교수|초빙교수|겸임교수|부교수|조교수|전임교수|특임교수|객원교수|연구교수|강사|직원|팀장|과장|주임|조교|행정실|행정직원)'
)
KOR_NAME_RE = re.compile(r'([가-힣]{2,4})\s*(?:교수|명예교수|부교수|조교수|직원|팀장|과장|주임|조교)')
OFFICE_HINTS = ("호실", "관", "층", "동", "실", "연구실", "Office", "Building")


@dataclass
class ContactRow:
    top_category: str
    seed_unit: str
    page_title: str
    source_url: str
    source_domain: str
    page_type: str
    unit_hint: str
    sub_unit_hint: str
    role_type: str
    name: str
    email: str
    phone: str
    office: str
    raw_context: str


def norm_url(base: str, href: str) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    if href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None
    abs_url = urljoin(base, href)
    abs_url, _ = urldefrag(abs_url)
    parsed = urlparse(abs_url)
    if parsed.scheme not in {"http", "https"}:
        return None
    return abs_url


def same_site(seed_url: str, candidate: str) -> bool:
    return urlparse(seed_url).netloc == urlparse(candidate).netloc


def looks_relevant(text: str, href: str) -> bool:
    s = f"{text} {href}".lower()
    if any(skip.lower() in s for skip in SKIP_PATTERNS):
        return False
    return any(p.lower() in s for p in FOLLOW_PATTERNS)


def compact_text(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '')).strip()


def unique_keep_order(items: Iterable[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def maybe_unit_from_title(title: str) -> tuple[str, str]:
    parts = [p.strip() for p in re.split(r'[\|\-·>]+', title) if p.strip()]
    if not parts:
        return "", ""
    # crude but useful: leftmost specific, rightmost generic
    sub_unit = parts[0]
    unit = parts[1] if len(parts) > 1 else parts[0]
    return unit, sub_unit


def infer_role_type(context: str) -> str:
    if "행정" in context or "staff" in context.lower():
        return "행정/직원"
    if "교수" in context or "faculty" in context.lower():
        return "교수"
    if "대표메일" in context:
        return "대표메일"
    return ""


def infer_name(context: str) -> str:
    m = KOR_NAME_RE.search(context)
    if m:
        return m.group(1)
    # fallback: first short Korean line-like token
    candidates = re.findall(r'[가-힣]{2,4}', context)
    blacklist = {"이메일", "연락처", "위치", "보직", "행정실", "교수진", "대학원", "학부", "학과", "전공"}
    for c in candidates:
        if c not in blacklist:
            return c
    return ""


def infer_phone(context: str) -> str:
    m = PHONE_RE.search(context)
    return m.group(0) if m else ""


def infer_office(context: str) -> str:
    lines = [compact_text(x) for x in re.split(r'[\n\r]+', context) if compact_text(x)]
    for line in lines:
        if any(h in line for h in OFFICE_HINTS):
            return line
    # fallback: sentence-level search
    m = re.search(r'([가-힣A-Za-z0-9\-\s]*?(?:관|동).*?(?:호실|실))', context)
    return compact_text(m.group(1)) if m else ""


def extract_contacts_from_dom(
    html: str,
    url: str,
    title: str,
    top_category: str,
    seed_unit: str,
    page,
) -> list[ContactRow]:
    soup = BeautifulSoup(html, "lxml")
    rows: list[ContactRow] = []
    domain = urlparse(url).netloc
    unit_hint, sub_unit_hint = maybe_unit_from_title(title)

    # 1) Explicit mailto links
    for a in soup.select('a[href^="mailto:"]'):
        href = a.get("href", "")
        email = href.split("mailto:", 1)[-1].split("?", 1)[0].strip()
        block = a
        for _ in range(5):
            if block is None:
                break
            if block.name in {"li", "tr", "article", "section", "div", "td"}:
                break
            block = block.parent
        context = compact_text(block.get_text(" ", strip=True) if block else a.get_text(" ", strip=True))
        rows.append(ContactRow(
            top_category=top_category,
            seed_unit=seed_unit,
            page_title=title,
            source_url=url,
            source_domain=domain,
            page_type=infer_role_type(context) or "mailto",
            unit_hint=unit_hint,
            sub_unit_hint=sub_unit_hint,
            role_type=infer_role_type(context),
            name=infer_name(context),
            email=email,
            phone=infer_phone(context),
            office=infer_office(context),
            raw_context=context[:1000],
        ))

    # 2) Plain text emails in text nodes
    text_nodes = soup.find_all(string=EMAIL_RE)
    for node in text_nodes:
        text = str(node)
        emails = EMAIL_RE.findall(text)
        parent = node.parent
        block = parent
        for _ in range(6):
            if block is None:
                break
            text_len = len(compact_text(block.get_text(" ", strip=True)))
            if block.name in {"li", "tr", "article", "section", "div", "td"} and 20 <= text_len <= 1200:
                break
            block = block.parent
        context = compact_text(block.get_text(" ", strip=True) if block else parent.get_text(" ", strip=True))
        for email in emails:
            rows.append(ContactRow(
                top_category=top_category,
                seed_unit=seed_unit,
                page_title=title,
                source_url=url,
                source_domain=domain,
                page_type=infer_role_type(context) or "text-email",
                unit_hint=unit_hint,
                sub_unit_hint=sub_unit_hint,
                role_type=infer_role_type(context),
                name=infer_name(context),
                email=email,
                phone=infer_phone(context),
                office=infer_office(context),
                raw_context=context[:1000],
            ))

    # 3) Representative email labels on admin pages (e.g. "대표메일:")
    full_text = soup.get_text("\n", strip=True)
    for m in re.finditer(r'(대표메일|대표 메일)\s*[:：]?\s*(' + EMAIL_RE.pattern + r')', full_text, re.I):
        context = compact_text(m.group(0))
        rows.append(ContactRow(
            top_category=top_category,
            seed_unit=seed_unit,
            page_title=title,
            source_url=url,
            source_domain=domain,
            page_type="대표메일",
            unit_hint=unit_hint,
            sub_unit_hint=sub_unit_hint,
            role_type="대표메일",
            name="",
            email=m.group(2),
            phone="",
            office="",
            raw_context=context,
        ))

    # 4) JS/DOM inspection fallback:
    #    some pages keep email in element attrs or in expanded detail sections not obvious in plain HTML.
    try:
        elements = page.locator("text=/@/")
        count = min(elements.count(), 200)
        for i in range(count):
            txt = compact_text(elements.nth(i).inner_text(timeout=500))
            for email in EMAIL_RE.findall(txt):
                rows.append(ContactRow(
                    top_category=top_category,
                    seed_unit=seed_unit,
                    page_title=title,
                    source_url=url,
                    source_domain=domain,
                    page_type="dom-text",
                    unit_hint=unit_hint,
                    sub_unit_hint=sub_unit_hint,
                    role_type=infer_role_type(txt),
                    name=infer_name(txt),
                    email=email,
                    phone=infer_phone(txt),
                    office=infer_office(txt),
                    raw_context=txt[:1000],
                ))
    except Exception:
        pass

    # 5) Hidden/image-only email cases:
    #    keep a row if we can see "이메일" but not the value, so user can later fill blanks manually.
    if not rows and ("이메일" in full_text or "대표메일" in full_text):
        context = compact_text(full_text[:1000])
        rows.append(ContactRow(
            top_category=top_category,
            seed_unit=seed_unit,
            page_title=title,
            source_url=url,
            source_domain=domain,
            page_type="email-present-but-hidden",
            unit_hint=unit_hint,
            sub_unit_hint=sub_unit_hint,
            role_type=infer_role_type(context),
            name="",
            email="",
            phone=infer_phone(context),
            office=infer_office(context),
            raw_context=context,
        ))

    return rows


def dedupe_rows(rows: list[ContactRow]) -> list[ContactRow]:
    seen = set()
    out = []
    for r in rows:
        key = (
            r.source_url,
            r.name.strip().lower(),
            r.email.strip().lower(),
            r.phone.strip(),
            r.office.strip(),
            r.role_type.strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def crawl_seed(browser, seed: dict[str, str], max_pages_per_site: int = 50, headless: bool = True) -> list[ContactRow]:
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    page.set_default_timeout(15000)

    seed_url = seed["url"]
    top_category = seed["top_category"]
    seed_unit = seed["unit"]

    visited: set[str] = set()
    queue = deque([seed_url])
    rows: list[ContactRow] = []

    while queue and len(visited) < max_pages_per_site:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        try:
            page.goto(url, wait_until="domcontentloaded")
            # Some pages need a short settle time.
            page.wait_for_timeout(1200)
        except PlaywrightTimeoutError:
            print(f"[WARN] timeout: {url}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"[WARN] goto failed: {url} -> {e}", file=sys.stderr)
            continue

        # Best-effort expanders
        for label in ["프로필 더 보기", "상세정보", "더보기", "more", "More"]:
            try:
                matches = page.get_by_text(label, exact=False)
                n = min(matches.count(), 100)
                for i in range(n):
                    try:
                        matches.nth(i).click(timeout=300, force=True)
                        page.wait_for_timeout(100)
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            html = page.content()
        except Exception:
            continue

        title = compact_text(page.title() or "")
        page_rows = extract_contacts_from_dom(html, page.url, title, top_category, seed_unit, page)
        rows.extend(page_rows)

        soup = BeautifulSoup(html, "lxml")
        candidates = []
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            text = compact_text(a.get_text(" ", strip=True))
            nxt = norm_url(page.url, href)
            if not nxt:
                continue
            if not same_site(seed_url, nxt):
                continue
            if nxt in visited:
                continue
            if looks_relevant(text, href):
                candidates.append(nxt)

        # Keep homepage-local paths first, then the rest.
        for nxt in unique_keep_order(candidates):
            if nxt not in visited and len(queue) < max_pages_per_site * 2:
                queue.append(nxt)

    context.close()
    return dedupe_rows(rows)


def write_csv(rows: list[ContactRow], output_path: str) -> None:
    fieldnames = list(asdict(rows[0]).keys()) if rows else list(ContactRow(
        top_category="", seed_unit="", page_title="", source_url="", source_domain="", page_type="",
        unit_hint="", sub_unit_hint="", role_type="", name="", email="", phone="", office="", raw_context=""
    ).__dict__.keys())
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="kookmin_contacts.csv")
    ap.add_argument("--headless", default="true", choices=["true", "false"])
    ap.add_argument("--max-pages-per-site", type=int, default=50)
    ap.add_argument("--limit-seeds", type=int, default=0, help="0 means all seeds")
    args = ap.parse_args()

    use_headless = args.headless.lower() == "true"
    seeds = SEEDS[:args.limit_seeds] if args.limit_seeds else SEEDS

    all_rows: list[ContactRow] = []
    started = time.time()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=use_headless)
        for idx, seed in enumerate(seeds, start=1):
            print(f"[{idx}/{len(seeds)}] crawling {seed['top_category']} / {seed['unit']} / {seed['url']}", file=sys.stderr)
            try:
                rows = crawl_seed(browser, seed, max_pages_per_site=args.max_pages_per_site, headless=use_headless)
                all_rows.extend(rows)
                print(f"    -> {len(rows)} rows", file=sys.stderr)
            except Exception as e:
                print(f"[ERROR] seed failed: {seed['url']} -> {e}", file=sys.stderr)
        browser.close()

    all_rows = dedupe_rows(all_rows)
    write_csv(all_rows, args.output)

    elapsed = time.time() - started
    print(f"done: {len(all_rows)} rows -> {args.output} ({elapsed:.1f}s)", file=sys.stderr)


if __name__ == "__main__":
    main()
