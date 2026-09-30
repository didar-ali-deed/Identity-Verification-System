def serialize_result(result) -> dict:
    scores = {f"channel_{key}": getattr(result, f"channel_{key}_score") for key in "abcde"}
    scored = result.stage_results is None or any(stage["stage"] == 6 for stage in result.stage_results)
    return {
        "id": result.id,
        "pipeline_version": result.pipeline_version,
        **{f"stage_{stage}_result": getattr(result, f"stage_{stage}_result") for stage in range(5)},
        "channel_scores": scores if any(value is not None for value in scores.values()) else None,
        "weighted_total": result.weighted_total if scored else None,
        "hard_rules_result": result.hard_rules_result,
        "decision_override": result.decision_override,
        "final_decision": result.final_decision,
        "flags": result.flags,
        "reason_codes": result.reason_codes,
        "started_at": result.started_at,
        "completed_at": result.completed_at,
        "stage_results": result.stage_results,
    }
