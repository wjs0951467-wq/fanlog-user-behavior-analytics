"""eval/ablation.py 테스트: 구성별로 무엇이 바뀌는지, 그리고 어떤 경우에도 원래대로 돌아오는지.

LLM, DB, 프로파일 파일은 모두 가짜다 (실제 호출 0회). app/ 의 코드는 고치지 않고 실행 중에만 바꿨다가 되돌린다.
"""
import json

import pytest

from app import text2sql, tools
from eval import ablation

PROFILE = {
    "dim_user": {"kind": "table", "row_count": 1750, "columns": {
        "user_id": {"type": "character varying"},
        "acquisition_channel": {"type": "character varying", "values": {"direct": 518, "search": 373}},
        "signup_date_kst": {"type": "date", "min": "2024-01-02", "max": "2026-03-31"}}},
    "mart_user_daily": {"kind": "view", "row_count": 133206, "columns": {
        "activity_status": {"type": "text", "values": {"active": 127318}}}},
    "meta_generation_run": {"kind": "table", "row_count": 1, "columns": {"run_id": {"type": "integer"}}},
}
APP_PROMPT = "APP PROMPT (JSON) === SEMANTIC LAYER ==="


def app_prompt():
    return APP_PROMPT


@pytest.fixture(autouse=True)
def fake_app(monkeypatch):
    """프로파일 파일과 시맨틱 레이어 파일을 읽지 않게 한다. 여기서 끼운 것이 이 테스트들의 "원래 상태"다."""
    monkeypatch.setattr(text2sql, "load_profile", lambda: PROFILE)
    monkeypatch.setattr(text2sql, "build_system_prompt", app_prompt)


def state():
    return (text2sql.build_system_prompt, text2sql.MAX_SQL_CALLS, text2sql.SYSTEM_RULES, text2sql.load_profile,
            text2sql.ask, text2sql.render_schema, tools.TOOLS["ask_data"]["llm_cost"])


class FakeLLM:
    def __init__(self, *replies):
        self.replies, self.systems = list(replies), []

    def __call__(self, system, messages, json_mode=False):
        self.systems.append(system)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return {"text": reply, "tokens": 10}


BLOCKED = json.dumps({"sql": "SELECT * FROM secret_table", "assumptions": []})       # 가드레일에 막히는 SQL
FALSE_REFUSAL = json.dumps({"sql": None, "cannot_answer": "없음", "missing": ["dim_user"]})  # 실제로 있는 테이블


# ---------- 구성 정의 ----------
def test_there_are_four_configs_in_order():
    assert ablation.CONFIGS == ("A", "B", "C", "D") and set(ablation.DESCRIPTIONS) == set(ablation.CONFIGS)


def test_calls_per_question():
    assert [ablation.calls_per_question(c) for c in "ABCD"] == [1, 1, 1, 3]
    assert ablation.FULL_SQL_CALLS == 3


@pytest.mark.parametrize("bad", ["E", "a", "", None, "AB"])
def test_unknown_config_is_rejected_before_anything_is_changed(bad):
    before = state()
    with pytest.raises(ValueError):
        ablation.calls_per_question(bad)
    with pytest.raises(ValueError):
        with ablation.applied(bad):
            pytest.fail("들어오면 안 된다")
    assert state() == before and ablation.is_restored()


# ---------- 구성별 프롬프트 ----------
def test_config_a_shows_schema_only():
    with ablation.applied("A"):
        prompt = text2sql.build_system_prompt()
        assert text2sql.MAX_SQL_CALLS == 1
    assert text2sql.SYSTEM_RULES in prompt and "=== SCHEMA ===" in prompt
    assert "- acquisition_channel: character varying" in prompt and "VIEW mart_user_daily" in prompt
    for absent in ("direct", "518", "2024-01-02", "1,750", "rows)", "values=", "range=", "SEMANTIC LAYER ===",
                   "SCHEMA PROFILE", "meta_generation_run"):
        assert absent not in prompt.replace(text2sql.SYSTEM_RULES, ""), absent


def test_config_b_adds_values_but_not_the_semantic_layer():
    with ablation.applied("B"):
        prompt = text2sql.build_system_prompt()
        assert text2sql.MAX_SQL_CALLS == 1
    body = prompt.replace(text2sql.SYSTEM_RULES, "")
    assert "=== SCHEMA PROFILE ===" in body and '"direct": 518' in body and "range=2024-01-02 .. 2026-03-31" in body
    assert "(1,750 rows)" in body
    assert "SEMANTIC LAYER ===" not in body and "meta_generation_run" not in body


def test_config_c_uses_the_app_prompt_without_retries():
    with ablation.applied("C"):
        assert text2sql.build_system_prompt is app_prompt and text2sql.build_system_prompt() == APP_PROMPT
        assert text2sql.MAX_SQL_CALLS == 1


def test_config_d_changes_nothing():
    before = state()
    with ablation.applied("D"):
        assert state() == before
    assert state() == before


def test_available_tables_line_lists_only_allowed_tables():
    line = next(x for x in ablation.build_prompt("A").splitlines() if x.startswith("AVAILABLE TABLES:"))
    assert line == "AVAILABLE TABLES: dim_user, mart_user_daily"


def test_build_prompt_is_only_for_a_and_b():
    for config in ("C", "D"):
        with pytest.raises(ValueError):
            ablation.build_prompt(config)


# ---------- 원복 ----------
@pytest.mark.parametrize("config", ["A", "B", "C", "D"])
def test_everything_is_restored_after_a_normal_exit(config):
    before = state()
    with ablation.applied(config):
        pass
    assert state() == before and ablation.is_restored()
    assert text2sql.build_system_prompt is app_prompt and text2sql.MAX_SQL_CALLS == 3


@pytest.mark.parametrize("config", ["A", "B", "C", "D"])
@pytest.mark.parametrize("exc", [RuntimeError("안에서 오류"), KeyboardInterrupt(), ValueError("x")])
def test_everything_is_restored_even_when_the_body_raises(config, exc):
    before = state()
    with pytest.raises(type(exc)):
        with ablation.applied(config):
            assert not ablation.is_restored() or config == "D"
            raise exc
    assert state() == before and ablation.is_restored()
    assert text2sql.build_system_prompt is app_prompt and text2sql.MAX_SQL_CALLS == 3


def test_restored_when_the_prompt_builder_itself_fails(monkeypatch):
    def broken():
        raise RuntimeError("프로파일 없음")

    before_prompt = text2sql.build_system_prompt
    monkeypatch.setattr(text2sql, "load_profile", broken)
    with pytest.raises(RuntimeError):
        with ablation.applied("A"):
            text2sql.build_system_prompt()
    assert text2sql.build_system_prompt is before_prompt and text2sql.MAX_SQL_CALLS == 3 and ablation.is_restored()


def test_nesting_is_refused_and_the_outer_config_still_restores():
    before = state()
    with ablation.applied("A"):
        inside = state()
        with pytest.raises(RuntimeError, match="겹쳐서"):
            with ablation.applied("B"):
                pytest.fail("들어오면 안 된다")
        assert state() == inside  # 거부된 안쪽 시도가 바깥 구성을 건드리지 않았다
    assert state() == before and ablation.is_restored()


def test_configs_can_be_applied_one_after_another():
    before = state()
    for config in "ABCDA":
        with ablation.applied(config):
            pass
        assert state() == before


def test_is_restored_is_false_inside_a_changing_config():
    with ablation.applied("C"):
        assert ablation.is_restored() is False
    assert ablation.is_restored() is True


# ---------- ask() 와 맞물려서 ----------
@pytest.mark.parametrize("config, calls", [("A", 1), ("B", 1), ("C", 1), ("D", 3)])
def test_ask_retries_only_in_config_d(monkeypatch, config, calls):
    llm = FakeLLM(BLOCKED)  # 같은 응답을 반복한다: 재시도하면 호출 수가 늘어난다
    monkeypatch.setattr(text2sql, "complete", llm)
    with ablation.applied(config):
        out = text2sql.ask("질문", summarize_result=False)
    assert out["usage"]["llm_calls"] == calls == len(llm.systems)
    assert out["error"].startswith(f"[가드레일 차단] {calls}회 시도 후 실패")


def test_false_refusal_is_not_corrected_without_retries(monkeypatch):
    llm = FakeLLM(FALSE_REFUSAL)
    monkeypatch.setattr(text2sql, "complete", llm)
    with ablation.applied("C"):
        out = text2sql.ask("질문", summarize_result=False)
    assert out["usage"]["llm_calls"] == 1 and out["error"].startswith("[거짓 거절] 1회 시도 후 실패")
    assert out["attempts"][-1]["error_type"] == "false_refusal"


def test_false_refusal_is_corrected_in_config_d(monkeypatch):
    llm = FakeLLM(FALSE_REFUSAL, BLOCKED)
    monkeypatch.setattr(text2sql, "complete", llm)
    with ablation.applied("D"):
        out = text2sql.ask("질문", summarize_result=False)
    assert [a["error_type"] for a in out["attempts"]][:2] == ["false_refusal", "guard"]  # 교정 후 다시 물었다


def test_ask_sends_the_config_prompt_to_the_model(monkeypatch):
    seen = {}
    for config in "ABCD":
        llm = FakeLLM(BLOCKED)
        monkeypatch.setattr(text2sql, "complete", llm)
        with ablation.applied(config):
            text2sql.ask("질문", summarize_result=False)
        seen[config] = llm.systems[0]
    assert "=== SCHEMA ===" in seen["A"] and "=== SCHEMA PROFILE ===" in seen["B"]
    assert seen["C"] == APP_PROMPT == seen["D"]
    assert len({seen["A"], seen["B"], seen["C"]}) == 3


def test_app_is_back_to_normal_after_ask_raises_inside_a_config(monkeypatch):
    def explode(*args, **kwargs):
        raise KeyboardInterrupt()

    before = state()
    monkeypatch.setattr(text2sql, "validate_sql", explode)
    monkeypatch.setattr(text2sql, "complete", FakeLLM(BLOCKED))
    with pytest.raises(KeyboardInterrupt):
        with ablation.applied("A"):
            text2sql.ask("질문", summarize_result=False)
    monkeypatch.undo()
    monkeypatch.setattr(text2sql, "load_profile", lambda: PROFILE)
    assert text2sql.MAX_SQL_CALLS == 3 and ablation.is_restored()
    assert before[1] == text2sql.MAX_SQL_CALLS
