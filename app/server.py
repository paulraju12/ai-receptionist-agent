"""HTTP API: chat endpoint per tenant, leads list, widget + demo pages."""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from . import agent

STATIC = Path(__file__).resolve().parent.parent / "static"
ID_RE = re.compile(r"^[a-z0-9-]{1,64}$")

app = FastAPI(title="Automation Studio")
# The widget runs on client websites, so the chat API must accept cross-origin calls.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


class ChatIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    message: str = Field(min_length=1, max_length=2000)


def check_id(value: str) -> str:
    if not ID_RE.match(value):
        raise HTTPException(400, "bad id")
    return value


@app.get("/api/tenant/{tenant_id}")
def tenant_public(tenant_id: str):
    try:
        t = agent.load_tenant(check_id(tenant_id))
    except KeyError:
        raise HTTPException(404, "unknown tenant")
    return {k: t[k] for k in ("business_name", "assistant_name", "brand_color", "greeting")}


@app.post("/api/chat/{tenant_id}")
def chat(tenant_id: str, body: ChatIn):
    try:
        return agent.chat_turn(check_id(tenant_id), check_id(body.session_id), body.message)
    except KeyError:
        raise HTTPException(404, "unknown tenant")
    except agent.anthropic.AuthenticationError:
        raise HTTPException(500, "AI key missing or invalid - add ANTHROPIC_API_KEY to .env")
    except agent.anthropic.RateLimitError:
        raise HTTPException(503, "busy, please retry in a moment")
    except agent.anthropic.APIStatusError as e:
        raise HTTPException(502, f"AI service error {e.status_code}")
    except agent.anthropic.APIConnectionError:
        raise HTTPException(502, "could not reach AI service")


@app.get("/api/leads/{tenant_id}")
def leads(tenant_id: str, key: str = ""):
    # Simple owner key for now; real auth comes with the SaaS dashboard.
    if not key or key != os.environ.get("ADMIN_KEY", ""):
        raise HTTPException(401, "admin key required")
    return agent.list_leads(check_id(tenant_id))


@app.get("/widget.js")
def widget():
    return FileResponse(STATIC / "widget.js", media_type="application/javascript")


@app.get("/voice", response_class=HTMLResponse)
def voice_demo():
    return (STATIC / "voice.html").read_text()


@app.get("/", response_class=HTMLResponse)
def demo():
    return (STATIC / "demo.html").read_text()
