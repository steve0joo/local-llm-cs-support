"""평가 결과(outputs/eval-*.json) 비교표·그래프. 파일 읽기와 표 계산만 검사하고 그리기는 실행하지 않는다."""
import json

from training.router import compare


def _eval(path, model, agent, acc, f1, min_recall=("fx", 0.5)):
    path.write_text(json.dumps({"model": model, "path": "model_only", "agent_accuracy": agent, "accuracy": acc,
                                "macro_f1": f1, "min_recall": list(min_recall), "latency": {"p95": 0.1}}), encoding="utf-8")


def test_latest_result_per_model(tmp_path):
    _eval(tmp_path / "eval-20260930-100000.json", "a", 0.70, 0.60, 0.50)
    _eval(tmp_path / "eval-20260930-110000.json", "a", 0.80, 0.70, 0.60)      # 같은 모델의 더 나중 결과
    _eval(tmp_path / "eval-20260930-105000.json", "b", 0.75, 0.65, 0.55)
    rows = compare.load_results(tmp_path)
    assert [r["model"] for r in rows] == ["a", "b"]                            # 모델 이름순
    assert rows[0]["agent_accuracy"] == 0.80                                    # 최신 것만


def test_only_model_only_results_are_compared(tmp_path):
    _eval(tmp_path / "eval-1.json", "a", 0.8, 0.7, 0.6)
    real = json.loads((tmp_path / "eval-1.json").read_text()); real["path"] = "classify"
    (tmp_path / "eval-2.json").write_text(json.dumps(real))
    assert len(compare.load_results(tmp_path)) == 1
