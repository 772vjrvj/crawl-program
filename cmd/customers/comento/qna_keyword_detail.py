import re
import json
import urllib.parse
from pathlib import Path


FILE_PATH = "new 9.txt"


# cp1252로 잘못 풀린 UTF-8 한글 복구
CP1252_REV = {
    0x20AC: 0x80, 0x201A: 0x82, 0x0192: 0x83, 0x201E: 0x84, 0x2026: 0x85,
    0x2020: 0x86, 0x2021: 0x87, 0x02C6: 0x88, 0x2030: 0x89, 0x0160: 0x8A,
    0x2039: 0x8B, 0x0152: 0x8C, 0x017D: 0x8E, 0x2018: 0x91, 0x2019: 0x92,
    0x201C: 0x93, 0x201D: 0x94, 0x2022: 0x95, 0x2013: 0x96, 0x2014: 0x97,
    0x02DC: 0x98, 0x2122: 0x99, 0x0161: 0x9A, 0x203A: 0x9B, 0x0153: 0x9C,
    0x017E: 0x9E, 0x0178: 0x9F,
}


def fix_mojibake(s: str | None) -> str | None:
    if s is None:
        return None

    buf = bytearray()
    for ch in s:
        code = ord(ch)
        if code <= 0xFF:
            buf.append(code)
        elif code in CP1252_REV:
            buf.append(CP1252_REV[code])
        else:
            buf.extend(ch.encode("utf-8", errors="ignore"))

    return buf.decode("utf-8", errors="replace")


def find_one(pattern: str, text: str, flags: int = re.S):
    m = re.search(pattern, text, flags)
    return m.groups() if m else None


def main():
    text = Path(FILE_PATH).read_text(encoding="utf-8", errors="replace")

    result = {
        "route": {},
        "meta": {},
        "question": {},
        "answers": [],
    }

    # 1) route 파라미터
    company = find_one(r'\["company","(.*?)","d"\]', text)
    job = find_one(r'\["job","(.*?)","d"\]', text)
    slug = find_one(r'\["slug","(.*?)","d"\]', text)

    if company:
        result["route"]["company"] = urllib.parse.unquote(company[0])
    if job:
        result["route"]["job"] = urllib.parse.unquote(job[0])
    if slug:
        result["route"]["slug"] = urllib.parse.unquote(slug[0])

    # 2) 메타 정보
    title = find_one(r'\["\$","title","2",\{"children":"(.*?)"\}\]', text)
    description = find_one(r'\["\$","meta","3",\{"name":"description","content":"(.*?)"\}\]', text)
    keywords = find_one(r'\["\$","meta","4",\{"name":"keywords","content":"(.*?)"\}\]', text)
    canonical = find_one(r'\["\$","link","6",\{"rel":"canonical","href":"(.*?)"\}\]', text)

    if title:
        result["meta"]["title"] = fix_mojibake(title[0])
    if description:
        result["meta"]["description"] = fix_mojibake(description[0])
    if keywords:
        result["meta"]["keywords"] = fix_mojibake(keywords[0])
    if canonical:
        result["meta"]["canonical"] = canonical[0]

    # 3) questionNo
    qno = find_one(r'queryKey":\["job-questions","answers",\{"questionNo":(\d+)\}\]', text)
    if qno:
        result["question"]["questionNo"] = int(qno[0])

    # 4) 질문 본문
    # author:"$41" 앞쪽 질문 블록 기준
    question = find_one(
        r'"createdAt":"(.*?)","content":"(.*?)","category":"(.*?)","company":"(.*?)","job":"(.*?)","author":"\$41"',
        text
    )
    if question:
        created_at, content, category, company_name, job_name = question
        result["question"].update({
            "createdAt": created_at,
            "content": fix_mojibake(content),
            "category": fix_mojibake(category),
            "company": fix_mojibake(company_name),
            "job": fix_mojibake(job_name),
        })

    # 5) 답변 목록
    answer_pattern = re.compile(
        r'\{"no":(\d+),"content":"(.*?)","createdAt":"(.*?)","bookmarkCount":\d+,"likeCount":\d+,'
        r'"isAdopted":(true|false),"author":\{"answerCount":\d+,"no":(\d+),"nickname":(null|".*?"),'
        r'"belong":"(.*?)","grade":"(.*?)","job":"(.*?)","type":\d+,"profileImage":(?:null|".*?"),'
        r'"matchingAttributes":\[(.*?)\],"adoptionRate":(\d+),"isBot":(true|false)\},'
        r'"parentReplyNo":(?:null|\d+),"replies":\[(.*?)\]\}',
        re.S,
    )

    for m in answer_pattern.finditer(text):
        (
            no,
            content,
            created_at,
            is_adopted,
            author_no,
            nickname_raw,
            belong,
            grade,
            author_job,
            matching_attrs,
            adoption_rate,
            is_bot,
            replies_raw,
        ) = m.groups()

        nickname = None
        if nickname_raw != "null":
            nickname = fix_mojibake(json.loads(nickname_raw))

        result["answers"].append({
            "no": int(no),
            "content": fix_mojibake(content),
            "createdAt": created_at,
            "isAdopted": is_adopted == "true",
            "author": {
                "no": int(author_no),
                "nickname": nickname,
                "belong": fix_mojibake(belong),
                "grade": fix_mojibake(grade),
                "job": fix_mojibake(author_job),
                "adoptionRate": int(adoption_rate),
                "isBot": is_bot == "true",
            },
        })

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()