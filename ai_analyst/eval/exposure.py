"""오염 방지: 보류(heldout) 질문을 모델에 보인 뒤 시맨틱 레이어가 바뀌었는지 알아낸다.

왜 필요한가
  보류 질문은 "모델의 결과를 보고 정의를 고친 적이 없는 질문"이어야 일반화의 근거가 된다 (DESIGN.md Day 5 의 보류 질문 규칙).
  보류 질문을 한 번 평가한 뒤 semantic_layer.yaml 을 고치면, 그 수정이 보류 질문의 결과를 보고 한 것인지 구분할 수 없다.
  그래서 "처음 보인 때의 시맨틱 레이어 해시"를 문항마다 적어 두고, 지금 해시와 다르면 경고한다.

한계: 해시는 파일이 바뀐 사실만 알려준다. 주석만 고쳐도 경고가 뜬다 (놓치는 것보다 과하게 알리는 쪽을 골랐다).
      schema_profile.json 이나 SYSTEM_RULES 가 바뀐 것은 경고하지 않는다 (기록만 한다).
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMANTIC_PATH = ROOT / "semantic" / "semantic_layer.yaml"
PROFILE_PATH = ROOT / "semantic" / "schema_profile.json"
REGISTRY_NAME = "heldout_exposure.json"
WARNING = "보류 질문 노출 후 시맨틱 레이어가 바뀜: 해당 문항은 개발용으로 이동해야 함"


def file_sha256(path) -> str | None:
    """파일 내용의 sha256. 파일이 없으면 None (schema_profile.json 은 git 제외 파일이라 없을 수 있다)."""
    path = Path(path)
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_registry(path) -> dict:
    """노출 기록을 읽는다. 파일이 없으면 빈 기록. 깨져 있으면 조용히 비우지 않고 오류를 낸다 (기록을 잃으면 오염을 못 잡는다)."""
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"노출 기록 파일의 모양이 잘못됐다: {path}")
    return data


def record_exposure(path, question_ids, semantic_sha: str, run_id: str) -> dict:
    """보류 질문을 모델에 보였다는 사실을 적는다. 문항마다 "처음" 보인 때의 해시를 지키고, 그 뒤 실행은 횟수만 늘린다."""
    registry = load_registry(path)
    for qid in question_ids:
        entry = registry.get(qid)
        if entry is None:
            registry[qid] = {"first_run": run_id, "semantic_sha256": semantic_sha, "runs": 1}
        else:
            entry["runs"] = int(entry.get("runs", 1)) + 1
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return registry


def contaminated_ids(registry: dict, current_semantic_sha: str | None) -> list:
    """처음 보인 때와 지금의 시맨틱 레이어 해시가 다른 보류 문항의 id (정렬됨)."""
    return sorted(qid for qid, entry in registry.items()
                  if isinstance(entry, dict) and entry.get("semantic_sha256") != current_semantic_sha)
