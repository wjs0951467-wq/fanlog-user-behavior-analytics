"""eval/exposure.py 테스트: 시맨틱 레이어 해시, 보류 질문 노출 기록, 오염 판정."""
import hashlib
import json

import pytest

from eval import exposure as E

SHA_A, SHA_B = "a" * 64, "b" * 64


def test_file_sha256_matches_hashlib_and_changes_with_content(tmp_path):
    f = tmp_path / "semantic.yaml"
    f.write_bytes("지표: 1".encode("utf-8"))
    first = E.file_sha256(f)
    assert first == hashlib.sha256("지표: 1".encode("utf-8")).hexdigest() and len(first) == 64
    f.write_bytes("지표: 2".encode("utf-8"))
    assert E.file_sha256(f) != first


def test_missing_file_or_folder_gives_none(tmp_path):
    assert E.file_sha256(tmp_path / "없음.yaml") is None
    assert E.file_sha256(tmp_path) is None  # 폴더는 파일이 아니다


def test_real_semantic_layer_can_be_hashed():
    assert E.SEMANTIC_PATH.name == "semantic_layer.yaml" and len(E.file_sha256(E.SEMANTIC_PATH)) == 64


def test_registry_starts_empty_when_the_file_does_not_exist(tmp_path):
    assert E.load_registry(tmp_path / E.REGISTRY_NAME) == {}


def test_first_exposure_is_recorded_with_the_hash(tmp_path):
    path = tmp_path / "results" / E.REGISTRY_NAME  # 폴더가 없어도 만든다
    registry = E.record_exposure(path, ["H01", "H02"], SHA_A, "run_1")
    assert registry == {"H01": {"first_run": "run_1", "semantic_sha256": SHA_A, "runs": 1},
                        "H02": {"first_run": "run_1", "semantic_sha256": SHA_A, "runs": 1}}
    assert json.loads(path.read_text(encoding="utf-8")) == registry == E.load_registry(path)


def test_later_runs_keep_the_first_hash_and_only_count(tmp_path):
    """처음 보인 때의 해시를 덮어쓰면, 레이어를 고친 뒤 다시 실행하는 것만으로 오염 기록이 지워진다."""
    path = tmp_path / E.REGISTRY_NAME
    E.record_exposure(path, ["H01"], SHA_A, "run_1")
    registry = E.record_exposure(path, ["H01", "H02"], SHA_B, "run_2")
    assert registry["H01"] == {"first_run": "run_1", "semantic_sha256": SHA_A, "runs": 2}
    assert registry["H02"] == {"first_run": "run_2", "semantic_sha256": SHA_B, "runs": 1}


def test_recording_nothing_keeps_the_registry(tmp_path):
    path = tmp_path / E.REGISTRY_NAME
    E.record_exposure(path, ["H01"], SHA_A, "run_1")
    assert E.record_exposure(path, [], SHA_B, "run_2") == {"H01": {"first_run": "run_1", "semantic_sha256": SHA_A, "runs": 1}}


def test_contaminated_ids_are_those_seen_under_a_different_hash(tmp_path):
    path = tmp_path / E.REGISTRY_NAME
    E.record_exposure(path, ["H02", "H01"], SHA_A, "run_1")
    registry = E.record_exposure(path, ["H03"], SHA_B, "run_2")
    assert E.contaminated_ids(registry, SHA_A) == ["H03"]
    assert E.contaminated_ids(registry, SHA_B) == ["H01", "H02"]  # 정렬돼서 나온다
    assert E.contaminated_ids(registry, "c" * 64) == ["H01", "H02", "H03"]
    assert E.contaminated_ids({}, SHA_A) == []


def test_unknown_current_hash_counts_as_changed(tmp_path):
    registry = E.record_exposure(tmp_path / E.REGISTRY_NAME, ["H01"], SHA_A, "run_1")
    assert E.contaminated_ids(registry, None) == ["H01"]  # 지금 해시를 모르면 "같다"고 보지 않는다


@pytest.mark.parametrize("content", ["[1, 2]", '"글자"', "{깨진 json"])
def test_broken_registry_is_an_error_not_an_empty_registry(tmp_path, content):
    path = tmp_path / E.REGISTRY_NAME
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        E.load_registry(path)
    with pytest.raises(ValueError):
        E.record_exposure(path, ["H01"], SHA_A, "run_1")
    assert path.read_text(encoding="utf-8") == content  # 깨진 기록을 덮어쓰지 않는다


def test_registry_holds_only_ids_hashes_and_counts(tmp_path):
    path = tmp_path / E.REGISTRY_NAME
    E.record_exposure(path, ["H01"], SHA_A, "run_1")
    entry = json.loads(path.read_text(encoding="utf-8"))["H01"]
    assert set(entry) == {"first_run", "semantic_sha256", "runs"}  # 질문 문장도 결과 값도 없다


def test_warning_text_is_the_agreed_sentence():
    assert E.WARNING == "보류 질문 노출 후 시맨틱 레이어가 바뀜: 해당 문항은 개발용으로 이동해야 함"
