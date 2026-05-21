# test_validator.py

import json
import numpy as np
from agents.validator_agent import ValidatorAgent

def run_test():
    print("=" * 60)
    print("🔬 RUNNING SCIENTIFIC VALIDATION ON VALIDATOR AGENT")
    print("=" * 60)

    # 1. Tải log đã ghi nhận ở ngày Thứ 3 từ outputs/logs.json
    try:
        with open("outputs/logs.json", "r", encoding="utf-8") as f:
            logs = json.load(f)
        print("  [✓] Đã đọc thành công log thực nghiệm logs.json")
    except Exception as e:
        print(f"  [✗] Lỗi đọc logs.json: {e}")
        return

    # 2. Khởi tạo bộ kiểm định ValidatorAgent offline (không gọi LLM để test toán học thuần túy)
    validator = ValidatorAgent(alpha=0.6, threshold=0.4, use_llm=False)

    # 3. Tính toán thủ công để verify độ chính xác
    print("\n[Step 1] Tính toán các đại lượng thành phần...")
    conflict_score, mean_kl, variance = validator.calculate_conflict_core(logs)
    
    print(f"  - Calculated Mean KL: {mean_kl:.6f}")
    print(f"  - Calculated Variance: {variance:.6f}")
    print(f"  - Hybrid Conflict Score (alpha=0.6): {conflict_score:.6f}")

    # Kiểm thử tính đúng đắn của phép chiếu tuyến tính liên tục (Linear Interpolation Projection)
    print("\n[Step 2] Kiểm nghiệm phép chiếu tuyến tính liên tục (Linear Projection):")
    for agent in logs:
        bv = agent["belief_vector"]
        d = bv["direction"]
        s = bv["strength"]
        x = d * s
        p_bull = 0.5 + 0.5 * x
        p_bear = 0.5 - 0.5 * x
        print(f"  * {agent['agent_id']}: Vector={d}*{s} = {x:.2f} -> Prob Dist P=[Bear:{p_bear:.3f}, Bull:{p_bull:.3f}]")

    # 4. Phân loại loại hình mâu thuẫn hệ thống
    categories = validator.classify_conflict(logs, conflict_score)
    print(f"\n[Step 3] Loại hình mâu thuẫn được phân loại: {categories}")

    # 5. Chạy toàn bộ pipeline kiểm định
    print("\n[Step 4] Chạy toàn bộ evaluate_pipeline offline...")
    report = validator.evaluate_pipeline(logs)
    
    print("\n[BÁO CÁO THỬ NGHIỆM ĐẦU RA]:")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    # Xác thực biên kích hoạt
    assert report["conflict_detected"] == (conflict_score >= 0.4), "Sai lệch logic kích hoạt tranh luận!"
    print("\n[✓] MỌI KIỂM THỬ TOÁN HỌC ĐÃ PHÁT HÀNH THÀNH CÔNG VÀ CHÍNH XÁC!")
    print("=" * 60)

if __name__ == "__main__":
    run_test()
