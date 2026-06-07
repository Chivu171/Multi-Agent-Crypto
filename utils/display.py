import re


def _extract_steps(logic_path) -> list:
    """Trích danh sách steps từ bất kỳ định dạng logic_path nào."""
    steps = []

    if isinstance(logic_path, str):
        parts = re.split(r'(?<=[.?!])\s+(?=\d+\.)', logic_path.strip())
        steps = [p.strip() for p in parts if p.strip()]

    elif isinstance(logic_path, list):
        for item in logic_path:
            if isinstance(item, dict):
                text = (item.get("point") or item.get("description")
                        or item.get("step") or item.get("conclusion")
                        or item.get("analysis") or "")
                note = item.get("note", "")
                steps.append(f"{text} ({note})" if note else text)
            else:
                steps.append(str(item))

    elif isinstance(logic_path, dict):
        inner = (
            logic_path.get("steps")
            or logic_path.get("final_logic_path")
            or logic_path.get("logic_path")
            or logic_path.get("reasoning_steps")
            or []
        )
        if isinstance(inner, list):
            for item in inner:
                if isinstance(item, dict):
                    text = (item.get("point") or item.get("description")
                            or item.get("step") or item.get("analysis") or "")
                    note = item.get("note", "")
                    steps.append(f"{text} ({note})" if note else text)
                else:
                    steps.append(str(item))
        else:
            steps = [str(inner)]

    cleaned = []
    for s in steps:
        s = str(s).strip()
        s = re.sub(r'^\d+\.\s*', '', s)
        if s:
            cleaned.append(s)
    return cleaned


def print_logic_path(label: str, logic_path):
    """In logic_path dạng một câu văn hoàn chỉnh trên một dòng."""
    steps = _extract_steps(logic_path)
    if not steps:
        print(f"    Logic Path ({label}): (không có dữ liệu)")
        return
    sentence = " → ".join(str(s).strip() for s in steps)
    print(f"    Logic Path ({label}): {sentence}")
