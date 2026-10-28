"""Bound tool output structurally, retaining scalar conclusions and coverage."""
from __future__ import annotations

import json


def _compact(value, strings=2500, items=40):
    if isinstance(value, dict):
        pairs = list(value.items())
        result = {key: _compact(item, strings, items) for key, item in pairs[:80]}
        if len(pairs) > 80:
            result["_coverage_omitted_keys"] = [key for key, _ in pairs[80:]]
        return result
    if isinstance(value, list):
        if len(value) <= items or (all(isinstance(v, (int, float, bool, type(None))) for v in value) and len(value) <= 100):
            return [_compact(v, strings, items) for v in value]
        return {"_coverage": "array excerpt; full array retained by host", "total_items": len(value),
                "first_items": [_compact(v, strings, items) for v in value[:2]],
                "last_items": [_compact(v, strings, items) for v in value[-10:]]}
    if isinstance(value, str) and len(value) > strings:
        return value[:strings // 2] + "\n…[bounded excerpt; full text retained by host]…\n" + value[-strings // 2:]
    return value


def present(result, source_reference):
    projected = _compact(result)
    if len(json.dumps(projected, ensure_ascii=False)) > 24000:
        projected = _compact(result, strings=1000, items=12)
    if len(json.dumps(projected, ensure_ascii=False)) > 24000:
        projected = {"evidence_id": result["evidence_id"], "tool": result["tool"], "status": "PARTIAL",
                     "availability": "withheld", "reason": "result exceeds message budget; request narrower evidence, no scientific values supplied"}
    projected["model_coverage"] = {"scope": "bounded structural projection; complete host result preserved",
                                    "full_result": source_reference}
    return projected
