"""LLM 호출을 이 파일 한 곳에 모은다.

왜 한 곳인가:
- LLM 업체/모델을 바꿀 때 이 파일만 고치면 된다 (설계 원칙 6: LLM 교체 가능).
- 테스트에서 complete() 하나만 가짜로 바꾸면 실제 API 를 한 번도 부르지 않는다.
- 호출 수/토큰 수를 한 군데에서 세므로 공용 크레딧 관리가 쉽다.
"""
import os
from functools import lru_cache

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI()  # OPENAI_API_KEY 환경변수를 사용한다. 키를 코드에 쓰지 않는다.


def complete(system: str, messages: list[dict], json_mode: bool = False) -> dict:
    """LLM 을 1회 호출하고 {"text": 응답 문자열, "tokens": 총 토큰 수} 를 돌려준다.

    messages 는 [{"role": "user" | "assistant", "content": "..."}] 형태의 대화 이력이다.
    json_mode=True 면 응답이 반드시 JSON 객체 문자열로 온다 (SQL 생성용). 요약은 일반 텍스트라 False.
    """
    # 모델명은 호출 시점에 읽는다. import 시점에 읽으면 테스트에서 환경변수를 바꿔도 반영되지 않는다.
    model = os.getenv("FANLOG_MODEL")
    if not model:
        raise RuntimeError(".env 에 FANLOG_MODEL (사용 가능한 모델명)을 설정하세요.")

    full_messages = [{"role": "system", "content": system}, *messages]
    options = {}
    if json_mode:
        # OpenAI json_object 모드는 대화 어딘가에 "JSON" 이라는 단어가 없으면 400 에러를 낸다.
        # API 를 부르기 전에 미리 확인해서, 프롬프트 실수로 호출 1회를 날리지 않게 한다.
        if "json" not in " ".join(m["content"] for m in full_messages).lower():
            raise ValueError("json_mode 를 쓰려면 프롬프트에 'JSON' 이라는 단어가 들어 있어야 합니다.")
        options["response_format"] = {"type": "json_object"}

    resp = _client().chat.completions.create(model=model, messages=full_messages, **options)
    # content 가 None 으로 올 수 있다(모델이 응답을 거부한 경우 등). 빈 문자열로 바꿔
    # 호출한 쪽에서 "파싱 실패"로 자연스럽게 처리되게 한다.
    text = resp.choices[0].message.content or ""
    tokens = resp.usage.total_tokens if resp.usage else 0
    return {"text": text, "tokens": tokens}
