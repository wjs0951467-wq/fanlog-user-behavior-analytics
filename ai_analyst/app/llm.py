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

# 비용과 멈춤 방지 (공용 크레딧)
CLIENT_TIMEOUT_SECONDS = 60   # 응답이 이보다 늦으면 오류로 끝낸다
MAX_OUTPUT_TOKENS = 4000      # 응답 하나의 출력 상한. 질문당 호출 수 상한(10회)과 함께 질문 하나의 최대 비용을 막는다
# 출력 상한의 파라미터 이름. 모델에 따라 max_tokens 만 받거나 max_completion_tokens 만 받는다고 알려져 있다.
# 실제 호출 없이는 확인할 수 없으므로 D단계 첫 호출에서 확인한다. 안 되면 이 한 줄만 바꾼다.
OUTPUT_TOKEN_PARAM = "max_completion_tokens"


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    # max_retries=0: SDK 는 기본으로 실패한 요청을 몰래 다시 보낸다. 그러면 우리가 센 호출 수보다 실제 요청이 많아진다.
    # 재시도는 text2sql 의 재시도 루프(호출 수를 세는 곳) 한 곳에서만 한다.
    # OPENAI_API_KEY 환경변수를 사용한다. 키를 코드에 쓰지 않는다.
    return OpenAI(max_retries=0, timeout=CLIENT_TIMEOUT_SECONDS)


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

    options[OUTPUT_TOKEN_PARAM] = MAX_OUTPUT_TOKENS
    resp = _client().chat.completions.create(model=model, messages=full_messages, **options)
    # content 가 None 으로 올 수 있다(모델이 응답을 거부한 경우 등). 빈 문자열로 바꿔
    # 호출한 쪽에서 "파싱 실패"로 자연스럽게 처리되게 한다.
    text = resp.choices[0].message.content or ""
    tokens = resp.usage.total_tokens if resp.usage else 0
    return {"text": text, "tokens": tokens}


def complete_with_tools(system: str, messages: list[dict], tools: list[dict], allow_tools: bool = True) -> dict:
    """도구 호출(function calling)이 가능한 LLM 1회 호출.

    반환: {"text": 답변 문자열, "tool_calls": [{"id", "name", "arguments"(JSON 문자열)}], "tokens"}
    tool_calls 가 비어 있으면 모델이 도구 없이 최종 답을 한 것이다.
    allow_tools=False 면 도구를 못 부르게 막는다 (예산이 끝나 최종 답만 받아야 할 때).
    """
    model = os.getenv("FANLOG_MODEL")
    if not model:
        raise RuntimeError(".env 에 FANLOG_MODEL (사용 가능한 모델명)을 설정하세요.")
    resp = _client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, *messages],
        tools=tools,
        tool_choice="auto" if allow_tools else "none",
        # 한 번에 도구를 여러 개 부르면 질문당 호출 수의 상한을 정할 수 없다. 한 단계에 하나만 부르게 한다.
        parallel_tool_calls=False,
        **{OUTPUT_TOKEN_PARAM: MAX_OUTPUT_TOKENS},
    )
    message = resp.choices[0].message
    calls = [{"id": c.id, "name": c.function.name, "arguments": c.function.arguments}
             for c in (message.tool_calls or [])]
    return {"text": message.content or "", "tool_calls": calls,
            "tokens": resp.usage.total_tokens if resp.usage else 0}


# 아래 두 함수는 "도구를 불렀다 / 도구 결과가 이렇다"를 대화 이력에 넣는 OpenAI 형식이다.
# 이 형식을 llm.py 안에 가둬 두면, LLM 업체를 바꿀 때 agent.py 를 고치지 않아도 된다.
def assistant_message(reply: dict) -> dict:
    """complete_with_tools 의 결과를 대화 이력용 assistant 메시지로 바꾼다."""
    return {"role": "assistant", "content": reply["text"] or None,
            "tool_calls": [{"id": c["id"], "type": "function",
                            "function": {"name": c["name"], "arguments": c["arguments"]}}
                           for c in reply["tool_calls"]]}


def tool_message(call_id: str, content: str) -> dict:
    """도구 실행 결과를 대화 이력용 tool 메시지로 바꾼다. call_id 로 어느 호출의 결과인지 짝을 맞춘다."""
    return {"role": "tool", "tool_call_id": call_id, "content": content}
