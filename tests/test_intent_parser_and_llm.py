"""LLM JSON parsing + client behavior with a fake HTTP server."""

from __future__ import annotations

import json

import httpx
import pytest

from ai_pipeline.intent_router import IntentRouter
from ai_pipeline.llm_client import LLMClient, LLMError, parse_llm_json
from shared.schemas import Clarification, ClarificationReason, CommandRequest


@pytest.mark.parametrize(
    "raw",
    [
        '{"target":"kitchen","action":"ON","needs_clarification":false}',
        '```json\n{"target":"galley","action":"off"}\n```',
        'Sure.\n{"target":"bedroom","action":"STATUS","needs_clarification":false}\n',
    ],
)
def test_parse_llm_json_accepts_json_shapes(raw):
    parsed = parse_llm_json(raw)
    assert parsed.parse_error is None
    assert parsed.action in {"ON", "OFF", "STATUS"}


def test_parse_llm_json_rejects_garbage():
    parsed = parse_llm_json("I think you want lights")
    assert parsed.parse_error == ClarificationReason.NOT_UNDERSTOOD


def test_parse_llm_json_clarification_flag():
    parsed = parse_llm_json(
        '{"target":"","action":"ON","needs_clarification":true,"clarification_reason":"ambiguous_target"}'
    )
    assert parsed.needs_clarification is True


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/chat/completions"):
        body = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"target": "kitchen", "action": "ON", "needs_clarification": False}
                        )
                    }
                }
            ]
        }
        return httpx.Response(200, json=body)
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": []})
    return httpx.Response(404)


def test_llm_client_and_router_with_mock_http(registry, settings):
    client = httpx.Client(transport=httpx.MockTransport(_handler), base_url="http://llm.test/v1")
    llm = LLMClient(settings=settings, client=client)
    assert llm.health_check() is True
    assert "kitchen" in llm.generate_completion("turn kitchen on", zones=["Kitchen"])

    router = IntentRouter(registry=registry, settings=settings, llm_client=llm)
    result = router.interpret_text("please illuminate the cooking area")
    assert isinstance(result, (CommandRequest, Clarification))


def test_llm_client_raises_on_failure(settings):
    def boom(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    client = httpx.Client(transport=httpx.MockTransport(boom), base_url="http://llm.test/v1")
    llm = LLMClient(settings=settings, client=client)
    with pytest.raises(LLMError):
        llm.generate_completion("hello", zones=["Kitchen"])
