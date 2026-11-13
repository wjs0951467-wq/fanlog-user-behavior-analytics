"""ai_analyst/.gitignore 의 eval/results 규칙 테스트: 실행 결과는 제외하고 보류 질문 노출 기록만 추적한다. git 읽기 명령만 쓴다."""
import shutil
import subprocess
from pathlib import Path

import pytest

from eval import exposure

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git 이 없다")


def ignored(path: str) -> bool:
    """git check-ignore -q 의 종료 코드: 0 이면 제외됨, 1 이면 추적 대상 (파일이 없어도 규칙만 본다)."""
    code = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, capture_output=True).returncode
    assert code in (0, 1), "git check-ignore 가 오류로 끝났다"
    return code == 0


def test_run_results_are_ignored():
    for name in ("eval/results/run_20261112_093000.json", "eval/results/run_x.json", "eval/results/anything.txt",
                 "eval/results/sub/dir/file.json"):
        assert ignored(name), name


def test_the_exposure_registry_is_tracked():
    assert exposure.REGISTRY_NAME == "heldout_exposure.json"  # 이 이름을 바꾸면 .gitignore 도 같이 바꿔야 한다
    assert not ignored(f"eval/results/{exposure.REGISTRY_NAME}")


def test_only_the_registry_is_an_exception():
    assert ignored("eval/results/heldout_exposure.json.bak")
    assert ignored("eval/results/old/heldout_exposure.json")  # 하위 폴더의 같은 이름은 제외


def test_eval_code_and_inputs_are_still_tracked():
    for name in ("eval/questions.yaml", "eval/candidates.yaml", "eval/run_eval.py", "eval/verify/reference_queries.sql",
                 "eval/PROGRESS.md", "eval/README.md"):
        assert not ignored(name), name


def test_existing_rules_are_unchanged():
    for name in (".env", "logs/agent_20261112.jsonl", "semantic/schema_profile.json", "app/__pycache__/x.pyc"):
        assert ignored(name), name
