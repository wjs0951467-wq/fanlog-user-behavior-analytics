from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator

from .agent import MAX_QUESTION_CHARS, write_ask_log
from .text2sql import ask

app = FastAPI(title="FANLOG AI Analyst")


class AskRequest(BaseModel):
    # 길이 제한이 없으면 아주 긴 질문으로 토큰 비용을 키울 수 있다. 화면(에이전트)과 같은 500자로 맞춘다.
    question: str = Field(max_length=MAX_QUESTION_CHARS)

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("질문이 비어 있습니다.")
        return value


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask_endpoint(req: AskRequest):
    out = ask(req.question)  # Decimal/datetime 은 FastAPI 가 JSON 으로 자동 변환
    write_ask_log(out, "ask")  # 화면의 일일 합계가 이 호출도 세게 한다 (로그가 실패해도 응답은 돌려준다)
    return out
