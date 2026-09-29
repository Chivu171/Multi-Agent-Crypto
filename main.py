# main.py

import datetime
import json
import os
import sys
import uuid
from agents.financial_agent import run as financial_run
from agents.market_agent import run as market_run
from agents.sentiment_agent import run as sentiment_run
from agents.conflict_analyzer import ConflictAnalyzer
from agents.debate_agent import DebateAgent
from agents.mediator_agent import run_mediator
from utils import llm
from utils.display import print_logic_path
from utils.failures import describe_failure, explanation_status
from utils.thresholds import (
    DEFAULT_CONFLICT_ALPHA,
    DEFAULT_CONFLICT_THRESHOLD,
    SIGNAL_NEUTRAL_BAND,
    SIGNAL_STRONG_INTENSITY_FLOOR,
)

RUN_BUDGET_SECONDS = 300
# Result files are replaced only by a run whose explanations passed review.
PUBLISHED_STATUSES = {"ok", "degraded"}


def save_json(path, data):
    """Atomic write: readers never see half a file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def main():
    """Run the live pipeline; return the run status (also in outputs/run_status.json)."""
    run = {"run_id": uuid.uuid4().hex[:12],
           "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "status": "error", "reason": None, "errors": []}
    llm.set_deadline(RUN_BUDGET_SECONDS)
    try:
        _run_pipeline(run)
    except Exception as exc:
        failure = describe_failure(exc, stage="pipeline")
        run["errors"].append(failure)
        run.update(status=failure["status"], reason=failure["reason"])
        print(f"\n[FATAL] {failure['status']} ({failure['reason']}): {failure['message']}")
    finally:
        llm.set_deadline(None)
        run["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_json("outputs/run_status.json", run)
        print(f"\n  -> Trạng thái lần chạy: {run['status']} ({run['reason'] or 'ok'}) — 'outputs/run_status.json'")
    return run["status"]


def _run_pipeline(run):
    print("=" * 60)
    print("🚀 KÍCH HOẠT HỆ THỐNG PHÂN TÍCH TÀI CHÍNH MULTI-AGENT CRYPTO")
    print("=" * 60)

    # Step 1: Gather independent opinions from Specialist Agents
    print("\n[Step 1] Thu thập nhận định độc lập từ các Specialist Agents...")
    named_outputs = []
    for name, runner in (("Financial_Agent", financial_run), ("Market_Agent", market_run),
                         ("Sentiment_Agent", sentiment_run)):
        try:
            output = runner()
            print(f"  - {name}: {output['signal']} (Confidence: {output['confidence']})")
            print_logic_path("initial", output.get("logic_path"))
        except Exception as e:
            failure = describe_failure(e, stage="specialist", agent=name)
            run["errors"].append(failure)
            print(f"  - ERROR {name}: {failure['status']} ({failure['reason']}): {failure['message']}")
            output = None
        named_outputs.append((name, output))

    all_outputs = [o for _, o in named_outputs if o is not None]
    missing_agents = [name for name, o in named_outputs if o is None]

    if not all_outputs:
        # Never substitute predictions from an older run's logs.
        first = run["errors"][0]
        run.update(status=first["status"], reason=first["reason"])
        print("\n[FATAL] Cả 3 Specialist Agent đều thất bại; không dùng nhận định cũ. Dừng pipeline.")
        return

    # Step 4: Run Conflict Analyzer
    print("\n[Step 4] Khởi chạy Conflict Analyzer đo và phân tích mâu thuẫn...")
    analyzer = ConflictAnalyzer(alpha=DEFAULT_CONFLICT_ALPHA, threshold=DEFAULT_CONFLICT_THRESHOLD, use_llm=True)
    validation_result = analyzer.evaluate_pipeline(all_outputs, missing_agents=missing_agents)

    if len(all_outputs) < 2:
        run.update(status="insufficient_agents", reason=run["errors"][0]["status"])
    elif not validation_result.get("explanations_valid", True):
        status, reason = explanation_status(validation_result)
        run.update(status=status, reason=reason)
        print("\n[!] RCA/Debate có giải thích chưa đạt kiểm tra nguồn. "
              "Các cập nhật bị từ chối đã giữ trạng thái cũ; lần chạy này không phải pipeline đầy đủ hợp lệ.")
    else:
        run.update(status="degraded" if missing_agents else "ok",
                   reason=run["errors"][0]["status"] if missing_agents else None)

    if validation_result.get("degraded_mode"):
        print(
            f"\n[⚠ CẢNH BÁO] Đang chạy ở chế độ suy giảm (degraded mode): "
            f"thiếu {len(missing_agents)}/3 agent ({', '.join(missing_agents) or 'không rõ'}). "
            f"Kết quả bên dưới KHÔNG đại diện đầy đủ cho sự đồng thuận 3-agent."
        )

    # If the Conflict Analyzer already performed a debate, its results are stored in 'debate_updated_outputs'
    debate_outputs = validation_result.get('debate_updated_outputs')
    if debate_outputs:
        print("\n[Debate Results] (generated by ConflictAnalyzer):")
        for out in debate_outputs:
            print(f"Agent {out['agent_id']} final confidence: {out['confidence']:.3f}")
        final_outputs = debate_outputs
    else:
        final_outputs = all_outputs

    # Display validation metrics
    print("\n[KẾT QUẢ KIỂM ĐỊNH TOÁN HỌC & LOGIC]:")
    print(f"  - Chỉ số mâu thuẫn lai (Conflict Score): {validation_result['conflict_score']}")
    print(f"  - Sai biệt phân phối (Mean Pairwise KL): {validation_result['metrics']['mean_pairwise_kl']}")
    print(f"  - Phương sai quyết định (Decision Variance): {validation_result['metrics']['decision_variance']}")
    print(f"  - Phát hiện mâu thuẫn vượt ngưỡng (Conflict Detected): {validation_result['conflict_detected']}")
    print(f"  - Phân loại loại hình mâu thuẫn (Conflict Categories): {validation_result['conflict_categories']}")
    print(f"  - Kích hoạt Debate Module (Trigger Debate): {validation_result['trigger_debate_module']}")

    # Step 5: Aggregate signals using Mediator Agent
    print("\n[Step 5] Chạy Mediator Agent để hợp nhất tín hiệu...")
    mediator_result = run_mediator(final_outputs)
    score = mediator_result['S_final']
    if len(final_outputs) < 2:
        # Chỉ còn 1 (hoặc 0) specialist — S_final lúc này chỉ phản ánh ý kiến
        # của một agent, không phải kết quả hợp nhất đa-agent. Không nên gán
        # nhãn BUY/SELL như thể đó là quyết định đã qua đối chiếu chéo.
        intensity = "N/A"
        signal = "INSUFFICIENT_DATA"
    else:
        intensity = "STRONG" if abs(score) > SIGNAL_STRONG_INTENSITY_FLOOR else "WEAK"
        signal = (
            "BUY" if score > SIGNAL_NEUTRAL_BAND
            else ("SELL" if score < -SIGNAL_NEUTRAL_BAND else "NEUTRAL")
        )

    print(f"  - S_final: {score:.4f} | Intensity: {intensity} | Signal: {signal}")
    run.update(signal=signal, S_final=score)

    print("\n[BÁO CÁO PHÂN TÍCH NGUYÊN NHÂN RỄ CỐT - RCA REPORT]:")
    print("-" * 60)
    print(validation_result['root_cause_analysis'])
    print("-" * 60)

    if run["status"] not in PUBLISHED_STATUSES:
        run["validation_report"] = validation_result
        print(f"\n  -> Không ghi đè kết quả cũ trong outputs/ (status={run['status']}); chi tiết trong run_status.json")
        return
    for path, data in (("outputs/logs.json", all_outputs),
                       ("outputs/mediator_result.json", {**mediator_result, "run_id": run["run_id"]}),
                       ("outputs/validation_report.json", {**validation_result, "run_id": run["run_id"]})):
        save_json(path, data)
    print("\n  -> Đã lưu logs.json, mediator_result.json, validation_report.json")
    print("=" * 60)

if __name__ == "__main__":
    sys.exit(0 if main() in PUBLISHED_STATUSES else 1)
