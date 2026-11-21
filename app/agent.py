"""Support agent core: one conversation turn for one tenant, with lead capture."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import anthropic
import yaml

ROOT = Path(__file__).resolve().parent.parent
TENANTS_DIR = ROOT / "tenants"
DB_PATH = ROOT / "data" / "studio.db"
DEFAULT_MODEL = "claude-haiku-5-5"  # cheap for demos; set `model:` per tenant to upgrade a client

_client = None
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:3b"  # free, runs locally; good enough for demos


def claude():
    """Created on first use so the free (Ollama) mode works without any API key."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client

CAPTURE_LEAD_TOOL = {
    "name": "capture_lead",
    "description": (
        "Save a customer's contact details so the business can follow up. Call this "
        "once you have the customer's name, at least one contact method (phone or "
        "email), and what they need. Do not call it with made-up details."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Customer's name"},
            "phone": {"type": "string", "description": "Phone number, or empty string"},
            "email": {"type": "string", "description": "Email address, or empty string"},
            "need": {"type": "string", "description": "What the customer wants, in one sentence"},
            "urgency": {"type": "string", "enum": ["low", "normal", "urgent"]},
        },
        "required": ["name", "phone", "email", "need", "urgency"],
        "additionalProperties": False,
    },
}


# ---------- storage (SQLite now; swap for Postgres when this becomes the SaaS) ----------

def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY, tenant TEXT, created REAL,"
        " name TEXT, phone TEXT, email TEXT, need TEXT, urgency TEXT, session TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, tenant TEXT, updated REAL, history TEXT)"
    )
    return conn


def load_history(session_id: str) -> list:
    row = db().execute("SELECT history FROM sessions WHERE id=?", (session_id,)).fetchone()
    return json.loads(row[0]) if row else []


def save_history(session_id: str, tenant_id: str, history: list) -> None:
    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (id, tenant, updated, history) VALUES (?,?,?,?)",
            (session_id, tenant_id, time.time(), json.dumps(history)),
        )


def save_lead(tenant_id: str, session_id: str, lead: dict) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO leads (tenant, created, name, phone, email, need, urgency, session)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (tenant_id, time.time(), lead["name"], lead["phone"], lead["email"],
             lead["need"], lead["urgency"], session_id),
        )
        return cur.lastrowid


def list_leads(tenant_id: str) -> list[dict]:
    rows = db().execute(
        "SELECT id, created, name, phone, email, need, urgency FROM leads WHERE tenant=? ORDER BY id DESC",
        (tenant_id,),
    ).fetchall()
    keys = ["id", "created", "name", "phone", "email", "need", "urgency"]
    return [dict(zip(keys, r)) for r in rows]


# ---------- tenants ----------

def load_tenant(tenant_id: str) -> dict:
    path = TENANTS_DIR / f"{tenant_id}.yaml"
    if not path.is_file() or path.parent != TENANTS_DIR:
        raise KeyError(tenant_id)
    return yaml.safe_load(path.read_text())


def system_prompt(t: dict) -> str:
    return (
        f"You are {t['assistant_name']}, the website assistant for {t['business_name']}. "
        "You chat with customers on the business's website.\n\n"
        "How to behave:\n"
        "- Be warm, brief and practical: 1-3 short sentences per reply, like a friendly front-desk person.\n"
        "- Answer only from the business information below. If something isn't covered, say you're not "
        "sure and offer to have the team follow up. Never invent prices, times or policies.\n"
        "- Only quote a price if that exact service is listed with a price below. For any service not "
        "listed (for example crowns or implants), say you don't have that price and offer a callback.\n"
        "- Copy numbers exactly as written in the business information: never round, estimate or change a price, "
        "day or time. Say 'from' when the information says 'from'.\n"
        "- You can't give medical, legal or financial advice; suggest speaking with the team.\n"
        f"- {t.get('languages', '')}\n\n"
        f"Booking and follow-ups:\n{t['booking_rule']}\n"
        f"<business_information>\n{t['knowledge']}\n</business_information>"
    )


# ---------- one chat turn ----------

def chat_turn(tenant_id: str, session_id: str, user_text: str) -> dict:
    """Runs one customer message through the agent. Returns reply text and any captured lead."""
    tenant = load_tenant(tenant_id)
    if tenant.get("provider", "ollama") == "ollama":
        return _chat_turn_ollama(tenant, tenant_id, session_id, user_text)
    return _chat_turn_claude(tenant, tenant_id, session_id, user_text)


def _handle_lead(tenant_id: str, session_id: str, lead: dict) -> tuple[dict | None, str, bool]:
    ok = bool(lead.get("name")) and bool(lead.get("phone") or lead.get("email")) and bool(lead.get("need"))
    if not ok:
        return None, "Missing name, contact method or need; ask the customer for it.", True
    lead = {k: str(lead.get(k, "")) for k in ("name", "phone", "email", "need", "urgency")}
    lead["urgency"] = lead["urgency"] if lead["urgency"] in ("low", "normal", "urgent") else "normal"
    lead_id = save_lead(tenant_id, session_id, lead)
    return {**lead, "id": lead_id}, f"Saved lead #{lead_id}. The team will follow up.", False


def _chat_turn_ollama(tenant: dict, tenant_id: str, session_id: str, user_text: str) -> dict:
    import httpx
    history = load_history(session_id)
    history.append({"role": "user", "content": user_text})
    captured = None
    tool = {"type": "function", "function": {
        "name": CAPTURE_LEAD_TOOL["name"], "description": CAPTURE_LEAD_TOOL["description"],
        "parameters": CAPTURE_LEAD_TOOL["input_schema"]}}
    reply = "Thanks! Someone from our team will get back to you shortly."
    for _ in range(4):
        body = {"model": tenant.get("local_model", OLLAMA_MODEL), "stream": False,
            "options": {"temperature": 0.3},
            "messages": [{"role": "system", "content": system_prompt(tenant)}] + history}
        if tenant.get("tools", True):  # some local models (e.g. Gemma) don't support tool calling
            body["tools"] = [tool]
        r = httpx.post(OLLAMA_URL, timeout=120, json=body)
        r.raise_for_status()
        msg = r.json()["message"]
        history.append({k: msg[k] for k in ("role", "content", "tool_calls") if k in msg})
        calls = msg.get("tool_calls") or []
        if calls:
            for c in calls:
                args = c.get("function", {}).get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                lead, note, _err = _handle_lead(tenant_id, session_id, args)
                captured = lead or captured
                history.append({"role": "tool", "content": note})
            continue
        reply = (msg.get("content") or "").strip() or reply
        break
    save_history(session_id, tenant_id, history)
    return {"reply": reply, "lead": captured}


def _chat_turn_claude(tenant: dict, tenant_id: str, session_id: str, user_text: str) -> dict:
    history = load_history(session_id)
    history.append({"role": "user", "content": user_text})
    captured = None

    for _ in range(4):  # at most a few tool round-trips per customer message
        model = tenant.get("model", DEFAULT_MODEL)
        extra = {}
        if model != "claude-haiku-5-5":  # server-side refusal fallbacks aren't available on Haiku
            extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        response = claude().beta.messages.create(
            model=model,
            max_tokens=16000,
            system=[{"type": "text", "text": system_prompt(tenant), "cache_control": {"type": "ephemeral"}}],
            tools=[CAPTURE_LEAD_TOOL],
            messages=history,
            output_config={"effort": "low"},
            **extra,
        )
        # Keep the full content (incl. thinking blocks) so later turns stay valid.
        history.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in response.content]})

        if response.stop_reason == "refusal":
            reply = "Sorry, I can't help with that here. Please call the front desk and they'll be glad to help."
            break

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason == "tool_use" and tool_uses:
            results = []
            for tu in tool_uses:
                lead, note, err = _handle_lead(tenant_id, session_id, tu.input if isinstance(tu.input, dict) else {})
                captured = lead or captured
                block = {"type": "tool_result", "tool_use_id": tu.id, "content": note}
                if err:
                    block["is_error"] = True
                results.append(block)
            history.append({"role": "user", "content": results})
            continue

        reply = "".join(b.text for b in response.content if b.type == "text").strip()
        break
    else:
        reply = "Thanks! Someone from our team will get back to you shortly."

    save_history(session_id, tenant_id, history)
    return {"reply": reply, "lead": captured}
