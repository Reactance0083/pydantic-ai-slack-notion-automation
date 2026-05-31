"""
Slack → Notion Automation Scaffold
Receives Slack Events API webhooks, classifies each message with pydantic-ai,
and automatically creates Notion database entries for tasks, decisions, and blockers.

Setup: expose this with ngrok (dev) or any server, paste URL into Slack App → Event Subscriptions.
"""
import hashlib, hmac, os, time
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from pydantic_ai import Agent
from dotenv import load_dotenv
import httpx

load_dotenv()

SLACK_BOT_TOKEN      = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
NOTION_API_KEY       = os.getenv("NOTION_API_KEY", "")
NOTION_DATABASE_ID   = os.getenv("NOTION_DATABASE_ID", "")

_missing = [k for k, v in {
    "SLACK_BOT_TOKEN": SLACK_BOT_TOKEN,
    "SLACK_SIGNING_SECRET": SLACK_SIGNING_SECRET,
    "NOTION_API_KEY": NOTION_API_KEY,
    "NOTION_DATABASE_ID": NOTION_DATABASE_ID,
}.items() if not v]
if _missing:
    raise RuntimeError(f"Missing env vars: {', '.join(_missing)}")


# ── Pydantic output model ─────────────────────────────────────────────────────
class MessageIntent(BaseModel):
    should_capture: bool     # False = skip (casual chat, reactions)
    title: str               # clean 5-10 word title
    category: str            # task | decision | question | blocker | info
    priority: str            # high | medium | low
    summary: str             # 1 sentence
    tags: list[str]          # up to 4 relevant tags


# ── pydantic-ai classifier ────────────────────────────────────────────────────
classifier = Agent(
    "anthropic:claude-haiku-4-5",
    result_type=MessageIntent,
    system_prompt=(
        "Classify Slack messages to decide if they should be saved to Notion. "
        "Capture: action items, decisions, blockers, questions needing follow-up, important announcements. "
        "Skip: casual conversation, reactions, one-word replies, off-topic messages. "
        "Extract a clean title, assign category/priority, and write a 1-sentence summary."
    ),
)


# ── Notion helper ─────────────────────────────────────────────────────────────
async def create_notion_entry(
    intent: MessageIntent, original: str, channel: str, user: str
) -> str:
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Name":     {"title":       [{"text": {"content": intent.title}}]},
            "Category": {"select":      {"name": intent.category.capitalize()}},
            "Priority": {"select":      {"name": intent.priority.capitalize()}},
            "Tags":     {"multi_select": [{"name": t} for t in intent.tags[:4]]},
            "Source":   {"rich_text":   [{"text": {"content": f"Slack #{channel} · {user}"}}]},
        },
        "children": [{
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content":
                f"Summary: {intent.summary}\n\nOriginal message:\n{original}"
            }}]},
        }],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post("https://api.notion.com/v1/pages", json=payload, headers=headers)
        r.raise_for_status()
        return r.json().get("url", "")


# ── Slack signature verification ──────────────────────────────────────────────
def verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    if abs(time.time() - int(timestamp)) > 300:
        return False
    base_string = f"v0:{timestamp}:{body.decode()}"
    expected = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(), base_string.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="Slack→Notion Automation", version="1.0.0")


@app.post("/slack/events")
async def slack_events(request: Request, background: BackgroundTasks):
    body      = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "0")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")

    payload = await request.json()

    # Required during initial Slack App setup
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    event = payload.get("event", {})
    # Process only real user messages (skip bot messages and edited messages)
    if event.get("type") == "message" and not event.get("bot_id") and not event.get("subtype"):
        background.add_task(process_message, event)

    return {"ok": True}


async def process_message(event: dict):
    text    = event.get("text", "").strip()
    channel = event.get("channel", "unknown")
    user    = event.get("user", "unknown")

    if len(text) < 15:
        return  # too short to be meaningful

    result = await classifier.run(
        f"Slack channel: #{channel}\nUser ID: {user}\nMessage: {text}"
    )
    intent = result.data

    if not intent.should_capture:
        return

    notion_url = await create_notion_entry(intent, text, channel, user)

    # Reply in thread so the team knows it was captured
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            "https://slack.com/api/chat.postMessage",
            json={
                "channel":  channel,
                "thread_ts": event.get("ts"),
                "text": f":white_check_mark: Captured to Notion: {notion_url}",
            },
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        )


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
