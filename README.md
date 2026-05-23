# Slack → Notion Automation (pydantic-ai + FastAPI)

Automatically captures important Slack messages into a Notion database. Uses `pydantic-ai` to classify each message — skipping casual chat, capturing action items, decisions, blockers, and questions that need follow-up.

## What It Does

1. Receives Slack Events API webhooks
2. Verifies HMAC-SHA256 signature (production-safe)
3. Classifies the message with `claude-haiku-4-5` via pydantic-ai
4. If worth capturing → creates a Notion database entry with title, category, priority, tags, and summary
5. Replies in the Slack thread with a link to the Notion page

## Notion Database Schema

Your Notion database needs these properties:

| Property | Type |
|----------|------|
| Name | Title |
| Category | Select |
| Priority | Select |
| Tags | Multi-select |
| Source | Rich text |

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in .env with your credentials
uvicorn main:app --reload --port 8000
```

Expose locally with ngrok:
```bash
ngrok http 8000
# Paste https://YOUR_NGROK_URL/slack/events into Slack App → Event Subscriptions
```

## What Gets Captured

| Category | Examples |
|----------|---------|
| `task` | "Can you update the auth flow by Friday?" |
| `decision` | "We're switching to Postgres for the new service" |
| `blocker` | "Can't deploy — CI is broken on main" |
| `question` | "Does anyone know the Stripe webhook retry policy?" |
| `info` | "FYI the API rate limit is 1000 req/min" |

Skipped: "lol", "ok thanks", reactions, bot messages, edited messages.

## Structured Output (pydantic-ai)

```python
class MessageIntent(BaseModel):
    should_capture: bool
    title: str           # clean 5-10 word title
    category: str        # task | decision | question | blocker | info
    priority: str        # high | medium | low
    summary: str         # 1-sentence description
    tags: list[str]      # up to 4 tags
```

## Customization

- Change `classifier` model in `main.py` to `claude-sonnet-4-5` for higher accuracy
- Add more Notion properties by extending `create_notion_entry()`
- Filter by specific Slack channels by checking `event.get("channel")`

## Architecture

```
Slack → POST /slack/events → verify signature
         → classify (pydantic-ai, async background task)
         → create_notion_entry()
         → reply in thread with Notion URL
```

## Requirements

- Python 3.11+
- Slack App with `chat:write`, `channels:history` bot scopes
- Notion integration with access to your database
- Anthropic API key (uses claude-haiku-4-5, ~$0.001/100 messages)
