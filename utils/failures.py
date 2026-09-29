"""One failure vocabulary for live runs and backtests.

Statuses: ok | rejected_by_reviewer | json_invalid | api_error | data_error |
timeout_budget | not_run_quota | not_run_config. Only "ok" is a prediction.
"""
from utils.grounding import GroundingError
from utils.llm import DeadlineExceeded, LLMAPIError, LLMResponseError

# A rerun cannot change these without a deliberate --retry-rejected.
COMPLETED_STATUSES = {"ok", "rejected_by_reviewer"}


def classify_failure(exc):
    """Return (status, reason) for an exception; never a trading signal."""
    if isinstance(exc, DeadlineExceeded):
        return "timeout_budget", "time_budget"
    if isinstance(exc, LLMAPIError):
        return "api_error", exc.kind
    if isinstance(exc, GroundingError):
        audit = exc.audit
        if audit.get("status") == "json_invalid":
            return "json_invalid", audit.get("reason", "schema")
        return "rejected_by_reviewer", audit.get("reason", "review_rejected")
    if isinstance(exc, LLMResponseError):
        return "json_invalid", exc.kind
    return "error", type(exc).__name__


def describe_failure(exc, **context):
    status, reason = classify_failure(exc)
    record = {**context, "status": status, "reason": reason, "type": type(exc).__name__,
              "message": str(exc)[:500]}
    audit = getattr(exc, "audit", None)
    if audit is not None:
        record["audit"] = audit
    return record


def explanation_status(validation):
    """(status, reason) of a Conflict Analyzer result whose RCA/Debate explanation failed."""
    failure = validation.get("explanation_failure")
    status = "json_invalid" if failure == "json_invalid" else "rejected_by_reviewer"
    audits = [("rca", validation.get("rca_grounding") or {})]
    for out in validation.get("debate_updated_outputs") or []:
        audits += [(f"debate_round_{a.get('round')}", a) for a in out.get("debate_audit", [])]
    for stage, audit in audits:
        if audit.get("status") == failure:
            return status, f"{stage}:{audit.get('reason', failure)}"
    return status, failure
