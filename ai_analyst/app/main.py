from fastapi import FastAPI
from pydantic import BaseModel

from .text2sql import ask

app = FastAPI(title="FANLOG AI Analyst")


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask_endpoint(req: AskRequest):
    return ask(req.question)  # Decimal/datetime 은 FastAPI 가 JSON 으로 자동 변환
