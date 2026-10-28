"""Shared strict App Server event validation; no scientific or execution authority."""
from __future__ import annotations

import json

from .review_app_server import redacted


class ReviewEvents:
    """Requires current thread/turn/prompt and message/token state on the runner."""

    def _notification(self, method: str, params: dict):
        if method == "remoteControl/status/changed":
            if params.get("status") != "disabled":
                raise ValueError("unexpected active remote-control surface")
            return
        if method == "warning":
            if params.get("threadId") != self.thread_id or not isinstance(params.get("message"), str):
                raise ValueError("warning thread/message mismatch")
            self.backend_warnings.append(params["message"])
            return
        if method in {"account/updated", "account/rateLimits/updated"}:
            return
        if method == "error":
            raise ValueError(f"backend error: {redacted(params)}")
        if method in {"thread/started", "thread/status/changed", "thread/tokenUsage/updated"}:
            if params.get("threadId", params.get("thread", {}).get("id")) != self.thread_id:
                raise ValueError("notification thread mismatch")
            if method == "thread/tokenUsage/updated":
                self.token_usage = params.get("tokenUsage")
            return
        allowed = {"turn/completed", "turn/started", "item/started", "item/completed", "item/agentMessage/delta",
                   "item/reasoning/summaryTextDelta", "item/reasoning/summaryPartAdded", "item/reasoning/textDelta",
                   "turn/moderationMetadata"}
        if method not in allowed or params.get("threadId") != self.thread_id \
                or params.get("turn", {}).get("id", params.get("turnId")) != self.turn_id:
            raise ValueError("unexpected notification or turn mismatch")
        if method.startswith("item/"):
            self._item_event(method, params.get("item", {}))
        if method == "turn/completed":
            if params["turn"]["status"] != "completed":
                raise ValueError("diagnostic turn failed/interrupted")
            self.turn_completed = True

    def _item_event(self, method: str, item: dict):
        if item.get("type") == "userMessage":
            content = item.get("content", [])
            if len(content) != 1 or content[0].get("type") != "text" \
                    or content[0].get("text") != json.dumps(self.prompt, ensure_ascii=False):
                raise ValueError("user message differs from the reserved frozen input")
            return
        if item.get("type") not in {None, "agentMessage", "reasoning", "dynamicToolCall"}:
            raise ValueError("native activity or delegation forbidden")
        if method == "item/completed" and item.get("type") == "agentMessage":
            if not isinstance(item.get("id"), str) or not isinstance(item.get("text"), str):
                raise ValueError("model message identity/text missing")
            self.messages[item["id"]] = item["text"]
            self.message_phases[item["id"]] = item.get("phase")
