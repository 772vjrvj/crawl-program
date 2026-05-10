# -*- coding: utf-8 -*-

import os
import re
import json
import uuid
import requests
from dotenv import load_dotenv


load_dotenv()


class ClovaSentimentAnalyzer:
    def __init__(self):
        self.host = "https://clovastudio.stream.ntruss.com"
        self.model = "HCX-005"

        raw_api_key = os.getenv("CLOVA_STUDIO_API_KEY")

        if not raw_api_key:
            raise ValueError("CLOVA_STUDIO_API_KEY 값이 .env에 없습니다.")

        # Bearer 자동 보정
        if raw_api_key.startswith("Bearer "):
            self.api_key = raw_api_key
        else:
            self.api_key = "Bearer " + raw_api_key

    def analyze(self, comment):
        url = f"{self.host}/v3/chat-completions/{self.model}"

        headers = {
            "Authorization": self.api_key,
            "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "text/event-stream"
        }

        data = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "너는 유튜브 댓글 감정분석 API다. "
                        "입력된 댓글의 감정을 positive, negative, neutral 중 하나로 분류한다. "
                        "반드시 JSON 객체 1개만 출력한다. "
                        "마크다운 코드블록을 절대 사용하지 않는다. "
                        "```json, ``` 같은 문자열을 절대 출력하지 않는다. "
                        "JSON 밖에 설명 문장을 출력하지 않는다. "
                        "같은 JSON을 반복 출력하지 않는다. "
                        "출력 형식은 반드시 다음과 같다. "
                        "{\"sentiment\":\"positive\",\"score\":0.8,\"reason\":\"짧은 판단 이유\"} "
                        "sentiment 값은 반드시 positive, negative, neutral 중 하나만 사용한다. "
                        "score는 positive면 0.1에서 1.0, neutral이면 0, negative면 -1.0에서 -0.1 사이 값으로 준다."
                    )
                },
                {
                    "role": "user",
                    "content": f"댓글: {comment}"
                }
            ],
            "topP": 0.1,
            "topK": 0,
            "maxTokens": 120,
            "temperature": 0.0,
            "repetitionPenalty": 1.1,
            "stop": [],
            "seed": 0,
            "includeAiFilters": True
        }

        result_text = self._request_stream(url, headers, data)
        result_json = self._extract_first_json(result_text)

        if result_json is None:
            return {
                "sentiment": "neutral",
                "score": 0,
                "reason": "JSON 파싱 실패",
                "raw": result_text
            }

        return self._normalize_result(result_json)

    def _request_stream(self, url, headers, data):
        result_text = ""
        current_event = ""

        try:
            with requests.post(url, headers=headers, json=data, stream=True, timeout=60) as response:
                if response.status_code != 200:
                    print("HTTP_STATUS:", response.status_code)
                    print("ERROR_BODY:", response.text)
                    response.raise_for_status()

                for line in response.iter_lines():
                    if not line:
                        continue

                    line_text = line.decode("utf-8").strip()

                    # 예: event:token
                    if line_text.startswith("event:"):
                        current_event = line_text.replace("event:", "", 1).strip()
                        continue

                    # 예: data:{...}
                    if not line_text.startswith("data:"):
                        continue

                    # token 이벤트만 누적한다.
                    # result/final 이벤트까지 누적하면 같은 응답이 중복될 수 있다.
                    if current_event != "token":
                        continue

                    json_text = line_text.replace("data:", "", 1).strip()

                    if json_text == "[DONE]":
                        continue

                    try:
                        item = json.loads(json_text)
                    except json.JSONDecodeError:
                        continue

                    message = item.get("message", {})
                    content = message.get("content", "")

                    if content:
                        result_text += content

        except requests.exceptions.HTTPError as e:
            raise e
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"CLOVA 요청 실패: {e}")

        return result_text.strip()

    def _extract_first_json(self, text):
        if not text:
            return None

        # 마크다운 코드블록 제거
        clean_text = text.strip()
        clean_text = clean_text.replace("```json", "")
        clean_text = clean_text.replace("```JSON", "")
        clean_text = clean_text.replace("```", "")
        clean_text = clean_text.strip()

        # 앞뒤 잡문 제거: 첫 번째 { 위치 찾기
        start_idx = clean_text.find("{")

        if start_idx < 0:
            return None

        clean_text = clean_text[start_idx:]

        # JSONDecoder로 첫 번째 JSON 객체만 파싱
        # 뒤에 중복 JSON이나 잡문이 붙어도 첫 객체만 가져온다.
        try:
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(clean_text)
            return obj
        except json.JSONDecodeError:
            pass

        # fallback: 정규식으로 한 번 더 시도
        match = re.search(r"\{.*?\}", clean_text, re.DOTALL)

        if not match:
            return None

        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    def _normalize_result(self, result):
        sentiment = result.get("sentiment", "neutral")
        score = result.get("score", 0)
        reason = result.get("reason", "")

        if sentiment not in ["positive", "negative", "neutral"]:
            sentiment = "neutral"

        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0

        if sentiment == "positive" and score <= 0:
            score = 0.1

        if sentiment == "negative" and score >= 0:
            score = -0.1

        if sentiment == "neutral":
            score = 0

        return {
            "sentiment": sentiment,
            "score": score,
            "reason": str(reason)
        }


if __name__ == "__main__":
    analyzer = ClovaSentimentAnalyzer()

    comment = "이 영상 진짜 좋네요"
    result = analyzer.analyze(comment)

    print("감정분석 결과:")
    print(json.dumps(result, ensure_ascii=False, indent=2))