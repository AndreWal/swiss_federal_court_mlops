from __future__ import annotations

import json
from typing import Any

import httpx

from models import LlmClassification


SYSTEM_PROMPT = """You classify Swiss Federal Supreme Court judgments for a dataset.
Return only fields supported by the JSON schema. Use null when the evidence is insufficient.
Use the codebook categories when possible:
- party classes: natural, legal, state
- outcome: granted, partly granted, rejected, inadmissible, writeoff
- area_general: Öffentliches Recht, Privatrecht, Strafrecht
Area labels must be German.
"""


def build_prompt(context: dict[str, Any]) -> str:
    return (
        "Classify ambiguous fields from this judgment excerpt.\n\n"
        f"Topic: {context.get('topic')}\n"
        f"Issue: {context.get('issue')}\n"
        f"Parties: {context.get('parties')}\n"
        f"Holdings: {context.get('holdings')}\n"
        f"Text start: {context.get('text_start')}\n"
    )


class OllamaClient:
    def __init__(
        self,
        host: str,
        model: str,
        timeout: float = 120.0,
    ) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

    def classify(self, context: dict[str, Any]) -> LlmClassification:
        payload = {
            "model": self.model,
            "stream": False,
            "format": LlmClassification.model_json_schema(),
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(context)},
            ],
        }
        response = httpx.post(
            f"{self.host}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        message = data.get("message")
        if not isinstance(message, dict):
            raise ValueError("Ollama response did not include a message object")
        content = message.get("content")
        if not isinstance(content, str):
            raise ValueError("Ollama response message did not include string content")
        return LlmClassification.model_validate_json(content)


def apply_llm_classification(
    annotation: dict[str, Any],
    classification: LlmClassification,
) -> None:
    updates = classification.model_dump()
    for field in (
        "area_detailed",
        "area_intermediate",
        "area_general",
        "app_class",
        "resp_class",
        "outcome",
    ):
        value = updates.get(field)
        if annotation.get(field) is None and value is not None:
            annotation[field] = value
            annotation.setdefault("confidence", {})[field] = classification.confidence
            if classification.evidence:
                annotation.setdefault("evidence", {})[field] = classification.evidence

    if annotation.get("outcome_binary") is None:
        outcome = annotation.get("outcome")
        if outcome in {"granted", "partly granted"}:
            annotation["outcome_binary"] = True
        elif outcome in {"inadmissible", "rejected"}:
            annotation["outcome_binary"] = False


def mock_classification_json(**values: Any) -> str:
    data = LlmClassification(**values).model_dump()
    return json.dumps(data, ensure_ascii=False)
