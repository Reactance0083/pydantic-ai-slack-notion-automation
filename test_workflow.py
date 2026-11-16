"""Offline regression checks. No messages or provider requests are sent."""
import asyncio
import hashlib
import hmac
import os
import time
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

with patch.dict(os.environ, {key: "offline-test" for key in (
    "ANTHROPIC_API_KEY", "SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET",
    "NOTION_API_KEY", "NOTION_DATABASE_ID",
)}):
    import main


class WorkflowTests(unittest.TestCase):
    def test_signed_challenge_and_rejection(self):
        body = b'{"type":"url_verification","challenge":"test-challenge"}'
        timestamp = str(int(time.time()))
        digest = hmac.new(main.SLACK_SIGNING_SECRET.encode(),
                          b"v0:" + timestamp.encode() + b":" + body,
                          hashlib.sha256).hexdigest()
        client = TestClient(main.app)
        response = client.post("/slack/events", content=body, headers={
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": "v0=" + digest,
        })
        self.assertEqual(response.json(), {"challenge": "test-challenge"})
        self.assertEqual(client.post("/slack/events", content=body).status_code, 403)
        self.assertEqual(client.post("/slack/events", content=body, headers={
            "X-Slack-Request-Timestamp": "invalid",
        }).status_code, 403)
        self.assertFalse(main.verify_slack_signature(body, "1", "v0=" + digest))

    def test_typed_capture_and_skip(self):
        calls = []
        def handle(request):
            calls.append(request)
            if request.url.host == "api.notion.com":
                return httpx.Response(200, json={"url": "https://notion.test/record"})
            return httpx.Response(200, json={"ok": True})
        original_client = httpx.AsyncClient
        def offline_client(**kwargs):
            return original_client(transport=httpx.MockTransport(handle), trust_env=False, **kwargs)
        output = dict(should_capture=True, title="Follow up on deployment blocker",
                      category="blocker", priority="high", summary="Release needs attention.", tags=["release"])
        event = {"text": "The deployment is blocked and needs a follow-up.",
                 "channel": "test-channel", "user": "test-user", "ts": "1"}
        with patch.object(models, "ALLOW_MODEL_REQUESTS", False), \
             patch.object(main.httpx, "AsyncClient", side_effect=offline_client):
            with main.classifier.override(model=TestModel(custom_output_args=output)):
                asyncio.run(main.process_message(event))
            self.assertEqual([r.url.host for r in calls], ["api.notion.com", "slack.com"])
            self.assertIn(b"https://notion.test/record", calls[-1].content)
            calls.clear()
            output["should_capture"] = False
            with main.classifier.override(model=TestModel(custom_output_args=output)):
                asyncio.run(main.process_message(event))
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
