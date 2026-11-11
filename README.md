# Slack to Notion Workflow

A FastAPI integration reference for converting selected Slack messages into structured Notion records.

**[Portfolio](https://github.com/Reactance0083)** · **Status: implementation reference; live integration not revalidated in this refresh**

## Implemented flow

1. Receive `POST /slack/events`.
2. Verify the Slack signature and request age.
3. Handle the URL-verification challenge or select eligible user messages.
4. Classify with a typed PydanticAI output.
5. Create a Notion page and post its link in the Slack thread.

The schema includes title, category, priority, summary, tags, and a capture decision. The code skips bot messages, subtypes, and very short messages before classification.

## Setup

The application is in `main.py`.

```bash
python -m venv .venv
# Activate the environment for your shell.
python -m pip install -r requirements.txt
# Copy .env.example to .env and configure the variables below.
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Required configuration: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `NOTION_API_KEY`, `NOTION_DATABASE_ID`, and `ANTHROPIC_API_KEY`.

The Notion database must have `Name` (title), `Category` and `Priority` (select), `Tags` (multi-select), and `Source` (rich text). External integration tests create records and messages, so use a designated test channel and database.

## What to inspect

- `MessageIntent`: typed classification output.
- `verify_slack_signature`: HMAC comparison and five-minute age check.
- `process_message`: filtering, classification, and service handoff.
- `create_notion_entry`: structured database properties and source context.

## Limits

This is a small integration reference, without a durable queue, event deduplication, retry orchestration, or an independent accuracy evaluation. Current PydanticAI and service compatibility must be verified before use; the source uses `result_type` and `result.data`.

Review malformed-request handling, webhook replay/retry behavior, permissions, and service responses before deployment. Signature verification alone does not make a complete production service.

Developed with AI assistance. Documentation reviewed against source on November 10, 2026.
