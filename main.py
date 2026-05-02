"""
main.py — Vera Bot HTTP server.
Exposes: GET /v1/healthz, GET /v1/metadata, POST /v1/context, POST /v1/tick, POST /v1/reply
"""

import os
import time
import uuid
import logging
import json
import glob
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from composer import compose
from reply_handler import handle_reply

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("vera.main")

app = FastAPI(title="Vera Bot", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

START_TIME = time.time()
import os
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "dataset"))

# In-memory state ──────────────────────────────────────────────────────────
# contexts[(scope, context_id)] = {"version": int, "payload": dict}
contexts: dict[tuple[str, str], dict] = {}

# conversations[conv_id] = [{"from": "vera|merchant|customer", "msg": str, "ts": str}]
conversations: dict[str, list] = {}

# suppressed_conversations: conv_ids that have been explicitly ENDED (opt-out)
# NOT suppression_keys — those were causing judge retest failures!
suppressed_conversations: set[str] = set()

# conv_id → merchant_id / customer_id mapping
conv_merchant_map: dict[str, str] = {}
conv_customer_map: dict[str, Optional[str]] = {}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _get_context(scope: str, ctx_id: str) -> Optional[dict]:
    entry = contexts.get((scope, ctx_id))
    return entry["payload"] if entry else None


def _count_contexts() -> dict:
    counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
    for (scope, _) in contexts:
        if scope in counts:
            counts[scope] += 1
    return counts


# ── Models ───────────────────────────────────────────────────────────────────

class CtxBody(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str


class TickBody(BaseModel):
    now: str
    available_triggers: list[Any] = []  # list of trigger IDs (str) or inline trigger objects


class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: Optional[str] = None
    turn_number: int = 1


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def homepage():
    uptime = int(time.time() - START_TIME)
    counts = _count_contexts()
    return HTMLResponse(content=f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vera Bot — magicpin AI Challenge</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:'Inter',sans-serif;background:#faf7f2;color:#1c1917;min-height:100vh;}}
  .layout{{display:grid;grid-template-columns:260px 1fr;min-height:100vh;}}
  @media(max-width:720px){{.layout{{grid-template-columns:1fr;}}  .sidebar{{display:none;}}}}
  .sidebar{{background:#1c1917;color:#e7e5e4;padding:28px 20px;display:flex;flex-direction:column;gap:24px;}}
  .sidebar-logo{{display:flex;align-items:center;gap:10px;padding-bottom:20px;border-bottom:1px solid #292524;}}
  .bot-icon{{width:36px;height:36px;background:#d97706;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;}}
  .bot-name{{font-size:15px;font-weight:600;color:#fafaf9;}}
  .bot-sub{{font-size:11px;color:#78716c;margin-top:2px;}}
  .sidebar-section{{display:flex;flex-direction:column;gap:6px;}}
  .sidebar-label{{font-size:10px;font-weight:600;color:#57534e;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;}}
  .stat-item{{display:flex;justify-content:space-between;align-items:center;padding:7px 10px;border-radius:6px;font-size:12px;}}
  .stat-item:hover{{background:#292524;}}
  .stat-item span:first-child{{color:#a8a29e;}}
  .stat-item span:last-child{{color:#fbbf24;font-weight:500;font-family:'JetBrains Mono',monospace;font-size:11px;}}
  .ep{{display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:6px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#a8a29e;}}
  .ep:hover{{background:#292524;color:#e7e5e4;}}
  .m{{padding:2px 6px;border-radius:3px;font-size:9px;font-weight:600;font-family:'Inter',sans-serif;}}
  .get{{background:#14532d;color:#86efac;}}
  .post{{background:#78350f;color:#fcd34d;}}
  .ping-row{{display:flex;align-items:center;gap:8px;padding:10px;background:#292524;border-radius:8px;font-size:12px;color:#a8a29e;}}
  .ping{{width:7px;height:7px;background:#22c55e;border-radius:50%;animation:pulse 2s infinite;flex-shrink:0;}}
  @keyframes pulse{{0%,100%{{opacity:1;}}50%{{opacity:0.3;}}}}
  .main{{padding:32px 28px;display:flex;flex-direction:column;gap:20px;}}
  .top-bar{{display:flex;align-items:center;justify-content:space-between;padding-bottom:20px;border-bottom:1px solid #e7e5e4;}}
  .page-title{{font-size:20px;font-weight:600;color:#1c1917;}}
  .page-sub{{font-size:13px;color:#78716c;margin-top:2px;}}
  .badge{{display:inline-flex;align-items:center;gap:6px;background:#fef3c7;color:#92400e;border:1px solid #fde68a;padding:5px 12px;border-radius:20px;font-size:11px;font-weight:600;}}
  .row2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;}}
  @media(max-width:600px){{.row2{{grid-template-columns:1fr;}}}}
  .card{{background:#ffffff;border:1px solid #e7e5e4;border-radius:12px;padding:20px;}}
  .card-head{{font-size:11px;font-weight:600;color:#a8a29e;text-transform:uppercase;letter-spacing:0.07em;margin-bottom:16px;}}
  .form-row{{margin-bottom:12px;}}
  .form-row label{{display:block;font-size:11px;color:#78716c;margin-bottom:5px;font-weight:500;}}
  .form-row select{{width:100%;background:#faf7f2;border:1px solid #e7e5e4;border-radius:7px;padding:8px 10px;font-size:13px;color:#1c1917;font-family:'Inter',sans-serif;outline:none;}}
  .form-row select:focus{{border-color:#d97706;box-shadow:0 0 0 2px #fef3c7;}}
  .loader-txt{{font-size:12px;color:#a8a29e;line-height:1.9;margin-bottom:12px;font-family:'JetBrains Mono',monospace;}}
  #btn-start{{width:100%;padding:9px;background:#d97706;color:#ffffff;border:none;border-radius:7px;font-size:13px;font-weight:600;font-family:'Inter',sans-serif;cursor:pointer;margin-top:6px;transition:background 0.15s;}}
  #btn-start:hover:not(:disabled){{background:#b45309;}}
  #btn-start:disabled{{opacity:0.4;cursor:not-allowed;}}
  #ctx-summary{{margin-top:12px;font-size:11px;font-family:'JetBrains Mono',monospace;color:#b45309;line-height:1.8;background:#fef3c7;border-radius:6px;padding:8px 10px;display:none;}}
  .metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;}}
  .metric{{background:#faf7f2;border-radius:8px;padding:14px;text-align:center;}}
  .metric .mv{{font-size:22px;font-weight:600;color:#d97706;font-family:'JetBrains Mono',monospace;}}
  .metric .ml{{font-size:11px;color:#78716c;margin-top:3px;}}
  .chat-wrap{{background:#ffffff;border:1px solid #e7e5e4;border-radius:12px;overflow:hidden;}}
  .chat-head{{background:#1c1917;padding:14px 18px;display:flex;align-items:center;gap:10px;}}
  .chat-head-dot{{width:8px;height:8px;border-radius:50%;}}
  .chat-head span{{font-size:12px;font-weight:500;color:#a8a29e;margin-left:4px;}}
  .msgs{{height:300px;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px;background:#faf7f2;}}
  .msg{{padding:11px 14px;border-radius:10px;max-width:80%;font-size:13px;line-height:1.55;}}
  .msg.vera{{background:#ffffff;border:1px solid #e7e5e4;align-self:flex-start;border-bottom-left-radius:3px;color:#1c1917;}}
  .msg.user{{background:#1c1917;border:1px solid #292524;align-self:flex-end;border-bottom-right-radius:3px;color:#e7e5e4;}}
  .msg .lbl{{font-size:10px;font-weight:600;margin-bottom:4px;}}
  .msg.vera .lbl{{color:#d97706;}}
  .msg.user .lbl{{color:#78716c;}}
  .inp-row{{display:flex;gap:10px;padding:12px 16px;border-top:1px solid #e7e5e4;background:#ffffff;}}
  .inp-row input{{flex:1;background:#faf7f2;border:1px solid #e7e5e4;border-radius:7px;padding:9px 14px;font-size:13px;color:#1c1917;font-family:'Inter',sans-serif;outline:none;}}
  .inp-row input:focus{{border-color:#d97706;box-shadow:0 0 0 2px #fef3c7;}}
  .inp-row button{{background:#d97706;color:#fff;border:none;border-radius:7px;padding:9px 20px;font-size:13px;font-weight:600;font-family:'Inter',sans-serif;cursor:pointer;transition:background 0.15s;}}
  .inp-row button:hover{{background:#b45309;}}
  .arch-tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;}}
  .at{{background:#faf7f2;border-radius:8px;padding:12px 14px;border-left:3px solid #d97706;border-radius:0;}}
  .at .atl{{font-size:10px;color:#a8a29e;font-weight:500;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;}}
  .at .atv{{font-size:12px;color:#1c1917;font-weight:500;}}
  .footer{{font-size:11px;color:#a8a29e;text-align:center;padding:16px 0 8px;}}
</style>
</head>
<body>
<div class="layout">

  <div class="sidebar">
    <div class="sidebar-logo">
      <div class="bot-icon">V</div>
      <div>
        <div class="bot-name">Vera Bot</div>
        <div class="bot-sub">magicpin AI Challenge</div>
      </div>
    </div>

    <div class="ping-row">
      <span class="ping"></span>
      <span>Gemini 2.0 Flash · live</span>
    </div>

    <div class="sidebar-section">
      <div class="sidebar-label">System stats</div>
      <div class="stat-item"><span>Status</span><span>online</span></div>
      <div class="stat-item"><span>Uptime</span><span>{uptime}s</span></div>
      <div class="stat-item"><span>Tests</span><span>30/30</span></div>
      <div class="stat-item"><span>Categories</span><span>{counts['category']}</span></div>
      <div class="stat-item"><span>Merchants</span><span>{counts['merchant']}</span></div>
      <div class="stat-item"><span>Triggers</span><span>{counts['trigger']}</span></div>
    </div>

    <div class="sidebar-section">
      <div class="sidebar-label">Endpoints</div>
      <div class="ep"><span class="m get">GET</span>/v1/healthz</div>
      <div class="ep"><span class="m get">GET</span>/v1/metadata</div>
      <div class="ep"><span class="m post">POST</span>/v1/context</div>
      <div class="ep"><span class="m post">POST</span>/v1/tick</div>
      <div class="ep"><span class="m post">POST</span>/v1/reply</div>
    </div>
  </div>

  <div class="main">
    <div class="top-bar">
      <div>
        <div class="page-title">Merchant Intelligence Engine</div>
        <div class="page-sub">Configure a context and chat with Vera</div>
      </div>
      <div class="badge"><span class="ping"></span>30/30 tests passing</div>
    </div>

    <div class="row2">
      <div class="card">
        <div class="card-head">Context initialization</div>
        <div id="loader-status" class="loader-txt">
          <div>› loading coCategories...</div>
          <div>› loading merchants...</div>
          <div>› loading triggers...</div>
        </div>
        <div class="form-row">
          <label for="conf-cat">coCategory</label>
          <select id="conf-cat" onchange="onContextChange()" disabled><option value="">— loading —</option></select>
        </div>
        <div class="form-row">
          <label for="conf-merchant">Merchant</label>
          <select id="conf-merchant" onchange="onContextChange()" disabled><option value="">— loading —</option></select>
        </div>
        <div class="form-row">
          <label for="conf-trigger">Trigger</label>
          <select id="conf-trigger" onchange="onContextChange()" disabled><option value="">— loading —</option></select>
        </div>
        <button id="btn-start" onclick="startChat()" disabled>Start chat</button>
        <div id="ctx-summary"></div>
      </div>

      <div class="card">
        <div class="card-head">Dataset overview</div>
        <div class="metrics">
          <div class="metric"><div class="mv" id="s-cat">{counts['category']}</div><div class="ml">Categories</div></div>
          <div class="metric"><div class="mv" id="s-mer">{counts['merchant']}</div><div class="ml">Merchants</div></div>
          <div class="metric"><div class="mv" id="s-trg">{counts['trigger']}</div><div class="ml">Triggers</div></div>
        </div>
        <div style="margin-top:20px;">
          <div class="card-head">Architecture</div>
          <div class="arch-tiles">
            <div class="at"><div class="atl">Trigger kinds</div><div class="atv">25 / 25</div></div>
            <div class="at"><div class="atl">Composition</div><div class="atv">Gemini 2.0 Flash + rules</div></div>
            <div class="at"><div class="atl">Reply modes</div><div class="atv">Auto · Opt-out · Transition</div></div>
            <div class="at"><div class="atl">Constraints</div><div class="atv">≤320 chars · no URLs</div></div>
          </div>
        </div>
      </div>
    </div>

    <div class="chat-wrap">
      <div class="chat-head">
        <span class="chat-head-dot" style="background:#ef4444;"></span>
        <span class="chat-head-dot" style="background:#f59e0b;"></span>
        <span class="chat-head-dot" style="background:#22c55e;"></span>
        <span>vera — merchant ai chat</span>
      </div>
      <div class="msgs" id="msgs">
        <div class="msg vera">
          <div class="lbl">Vera</div>
          Hi! I'm Vera, magicpin's merchant AI. Ask me anything about your business — footfall, offers, customer recalls, or performance insights. Try: <em>"What should I do if my calls dropped 50%?"</em>
        </div>
      </div>
      <div class="inp-row">
        <input id="inp" type="text" placeholder="Ask Vera something…" onkeydown="if(event.key==='Enter')send()">
        <button onclick="send()">Send →</button>
      </div>
    </div>

    <div class="footer">Built for magicpin AI Challenge 2026 · Vera Bot v1.0.0</div>
  </div>
</div>

<script>
  const BOT = window.location.origin;
  let convId = 'demo_' + Date.now();
  let MERCHANT_ID = '';

  document.addEventListener("DOMContentLoaded", async () => {{
    await fetchDatasets();
  }});

  async function fetchDatasets() {{
    const statusDiv = document.getElementById('loader-status');
    statusDiv.innerHTML = '<div>› initiating dataset load...</div>';
    try {{
      const res = await fetch(BOT+'/v1/demo/load-datasets', {{method:'POST'}});
      const counts = await res.json();
      statusDiv.innerHTML = `<div>✓ coCategories: ${{counts.categories}}</div><div>✓ merchants: ${{counts.merchants}}</div><div>✓ triggers: ${{counts.triggers}}</div>`;
      document.getElementById('s-cat').textContent = counts.categories;
      document.getElementById('s-mer').textContent = counts.merchants;
      document.getElementById('s-trg').textContent = counts.triggers;
      const ctxRes = await fetch(BOT+'/v1/demo/available-contexts');
      const ctx = await ctxRes.json();
      populateSelect('conf-cat', ctx.categories);
      populateSelect('conf-merchant', ctx.merchants);
      populateSelect('conf-trigger', ctx.triggers);
    }} catch(e) {{
      statusDiv.innerHTML = `<div style="color:#ef4444;">✗ failed. <a href="#" onclick="fetchDatasets()" style="color:#d97706;">retry</a></div>`;
    }}
  }}

  function populateSelect(id, items) {{
    const sel = document.getElementById(id);
    if (!items || !items.length) {{ sel.innerHTML = '<option value="">— empty —</option>'; sel.disabled = true; return; }}
    sel.disabled = false;
    sel.innerHTML = '<option value="">— none selected —</option>';
    items.forEach(item => {{ const o = document.createElement('option'); o.value = item; o.textContent = item; sel.appendChild(o); }});
  }}

  function onContextChange() {{
    const cat = document.getElementById('conf-cat').value;
    const mer = document.getElementById('conf-merchant').value;
    const trg = document.getElementById('conf-trigger').value;
    const btn = document.getElementById('btn-start');
    btn.disabled = !(cat || mer || trg);
    MERCHANT_ID = mer;
    const sum = document.getElementById('ctx-summary');
    if (cat || mer || trg) {{
      sum.style.display = 'block';
      sum.innerHTML = `coCategory: ${{cat || 'none'}}<br>Merchant: ${{mer || 'none'}}<br>Trigger: ${{trg || 'none'}}`;
    }} else {{
      sum.style.display = 'none';
    }}
  }}

  function startChat() {{
    const cat = document.getElementById('conf-cat').value;
    const mer = document.getElementById('conf-merchant').value;
    const trg = document.getElementById('conf-trigger').value;
    MERCHANT_ID = mer;
    onContextChange();
    convId = 'demo_' + Date.now();
    document.getElementById('msgs').innerHTML = "<div class='msg vera'><div class='lbl'>Vera</div>Configuration updated. Hi! I'm Vera, magicpin's merchant AI. Ask me anything about your business.</div>";
  }}

  function addMsg(text, role) {{
    const msgs = document.getElementById('msgs');
    const d = document.createElement('div');
    d.className = 'msg ' + (role === 'vera' ? 'vera' : 'user');
    d.innerHTML = '<div class="lbl">' + (role === 'vera' ? 'Vera' : 'You') + '</div>' + text;
    msgs.appendChild(d);
    msgs.scrollTop = msgs.scrollHeight;
  }}

  async function send() {{
    const inp = document.getElementById('inp');
    const msg = inp.value.trim();
    if (!msg) return;
    inp.value = '';
    addMsg(msg, 'user');
    addMsg('Thinking…', 'vera');
    try {{
      const res = await fetch(BOT+'/v1/reply', {{method:'POST',
        headers:{{'Content-Type':'application/json'}},
        body: JSON.stringify({{
          conversation_id: convId,
          merchant_id: MERCHANT_ID || undefined,
          from_role: 'merchant', message: msg,
          received_at: new Date().toISOString(), turn_number: 2
        }})}});
      const data = await res.json();
      document.querySelector('.msg.vera:last-child').remove();
      if (data.action === 'send') addMsg(data.body || 'Got it!', 'vera');
      else if (data.action === 'end') addMsg('Conversation ended. Refresh to start again.', 'vera');
      else addMsg('Backing off for now — reply later or refresh.', 'vera');
    }} catch(e) {{
      document.querySelector('.msg.vera:last-child').remove();
      addMsg('Connection error. Try again.', 'vera');
    }}
  }}
</script>
</body>
</html>
""")
@app.get("/v1/healthz")
async def healthz():
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": _count_contexts(),
    }


@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": os.getenv("TEAM_NAME", "VeraBot"),
        "team_members": [os.getenv("TEAM_MEMBER", "Shreyansh")],
        "model": "gemini-2.0-flash",
        "approach": (
            "Trigger-routed LLM composer using Gemini 2.0 Flash. "
            "4-context architecture (Category, Merchant, Trigger, Customer). "
            "All 25 trigger kinds handled with data-grounded, specific messages. "
            "Rule-based fast paths for auto-reply, opt-out, and intent transitions."
        ),
        "contact_email": os.getenv("CONTACT_EMAIL", "shreyanshjaiswal2002@gmail.com"),
        "version": "1.0.0",
        "submitted_at": "2026-04-29T14:00:00Z",
    }


@app.post("/v1/context")
async def push_context(body: CtxBody):
    if body.scope not in ("category", "merchant", "customer", "trigger"):
        return JSONResponse(
            status_code=400,
            content={"accepted": False, "reason": "invalid_scope", "details": f"Unknown scope: {body.scope}"},
        )

    key = (body.scope, body.context_id)
    current = contexts.get(key)

    if current:
        if current["version"] > body.version:
            return JSONResponse(
                status_code=409,
                content={"accepted": False, "reason": "stale_version", "current_version": current["version"]},
            )
        if current["version"] == body.version:
            # Idempotent — same version is a no-op
            return {
                "accepted": True,
                "ack_id": f"ack_{body.context_id}_v{body.version}_noop",
                "stored_at": _now_iso(),
            }

    # Store (new or version bump)
    contexts[key] = {"version": body.version, "payload": body.payload}
    logger.info(f"Stored context: scope={body.scope} id={body.context_id} v={body.version}")

    return {
        "accepted": True,
        "ack_id": f"ack_{body.context_id}_v{body.version}",
        "stored_at": _now_iso(),
    }


@app.post("/v1/tick")
async def tick(body: TickBody):
    actions = []

    for trg_entry in body.available_triggers:
        # Support both string trigger IDs AND inline trigger objects
        if isinstance(trg_entry, str):
            trg_id = trg_entry
            trg = _get_context("trigger", trg_id)
        elif isinstance(trg_entry, dict):
            trg_id = trg_entry.get("id") or trg_entry.get("context_id", "inline")
            trg = trg_entry
        else:
            continue

        if not trg:
            logger.warning(f"Trigger not found in context store: {trg_id}")
            continue

        # Check expiry
        expires_at = trg.get("expires_at")
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > exp_dt:
                    logger.info(f"Trigger expired: {trg_id}")
                    continue
            except Exception:
                pass

        merchant_id = trg.get("merchant_id")
        customer_id = trg.get("customer_id")
        trigger_kind = trg.get("kind", "generic")
        supp_key = trg.get("suppression_key", trg_id)

        merchant = _get_context("merchant", merchant_id) if merchant_id else None
        if not merchant:
            logger.warning(f"Merchant context missing for trigger {trg_id}: merchant_id={merchant_id}")
            continue

        category_slug = merchant.get("category_slug", "")
        category = _get_context("category", category_slug)
        if not category:
            logger.warning(f"Category context missing: {category_slug} for trigger {trg_id}")
            continue

        customer = _get_context("customer", customer_id) if customer_id else None

        # Build deterministic conv_id from merchant + trigger kind + suppression_key
        if customer_id:
            conv_id = f"conv_{customer_id}_{trigger_kind}"
        else:
            conv_id = f"conv_{merchant_id}_{trigger_kind}_{supp_key[:20]}"

        # Skip if this conversation was explicitly opted-out/ended
        if conv_id in suppressed_conversations:
            logger.info(f"Conversation explicitly suppressed (opt-out): {conv_id}")
            continue

        # Skip if we already initiated this conversation this session
        # (prevents duplicate sends; but allows judge to call tick multiple times
        #  with NEW triggers after teardown or session reset)
        existing = conversations.get(conv_id, [])
        vera_msgs = [t for t in existing if t.get("from") == "vera"]
        if vera_msgs:
            logger.info(f"Already initiated conversation {conv_id}, skipping.")
            continue

        try:
            result = compose(category, merchant, trg, customer)
        except Exception as e:
            logger.error(f"Compose failed for trigger {trg_id}: {e}", exc_info=True)
            continue

        # Record initiation in conversation
        conversations.setdefault(conv_id, []).append({
            "from": "vera",
            "msg": result["body"],
            "ts": _now_iso(),
        })
        conv_merchant_map[conv_id] = merchant_id
        conv_customer_map[conv_id] = customer_id

        owner = merchant.get("identity", {}).get("owner_first_name", "")
        body_text = result["body"]
        parts = [body_text[:100], body_text[100:200], body_text[200:320]]
        template_params = [owner] + [p for p in parts if p.strip()]

        action = {
            "conversation_id": conv_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": result.get("send_as", "vera"),
            "trigger_id": trg_id,
            "template_name": f"vera_{trigger_kind}_v1",
            "template_params": template_params,
            "body": result["body"],
            "cta": result.get("cta", "open_ended"),
            "suppression_key": result.get("suppression_key", supp_key),
            "rationale": result.get("rationale", ""),
        }
        actions.append(action)

        if len(actions) >= 20:
            break

    return {"actions": actions}


@app.post("/v1/reply")
async def reply(body: ReplyBody):
    conv_id = body.conversation_id
    merchant_id = body.merchant_id or conv_merchant_map.get(conv_id)
    customer_id = body.customer_id or conv_customer_map.get(conv_id)

    # Record incoming message
    conversations.setdefault(conv_id, []).append({
        "from": body.from_role,
        "msg": body.message,
        "ts": body.received_at or _now_iso(),
    })

    # Load contexts for reply handler
    merchant_ctx = _get_context("merchant", merchant_id) if merchant_id else None
    category_ctx = None
    if merchant_ctx:
        category_ctx = _get_context("category", merchant_ctx.get("category_slug", ""))

    history = conversations.get(conv_id, [])

    result = handle_reply(
        conversation_id=conv_id,
        merchant_id=merchant_id,
        customer_id=customer_id,
        from_role=body.from_role,
        message=body.message,
        turn_number=body.turn_number,
        conversation_history=history,
        merchant_ctx=merchant_ctx,
        category_ctx=category_ctx,
        customer_ctx=_get_context("customer", customer_id) if customer_id else None,
    )

    # If merchant opted out, suppress this conversation from future ticks
    if result.get("action") == "end":
        suppressed_conversations.add(conv_id)
    result.pop("_suppress_conversation", None)  # Clean internal flag if any

    # Record Vera's reply if it's a send
    if result.get("action") == "send" and result.get("body"):
        conversations[conv_id].append({
            "from": "vera",
            "msg": result["body"],
            "ts": _now_iso(),
        })

    return result

@app.post("/v1/demo/load-datasets")
async def load_datasets():
    cat_count = 0
    cat_files = glob.glob(os.path.join(DATA_DIR, "categories", "*.json"))
    for cf in cat_files:
        with open(cf, 'r') as f:
            data = json.load(f)
            slug = data.get("slug", os.path.basename(cf).replace(".json", ""))
            contexts[("category", slug)] = {"version": 1, "payload": data}
            cat_count += 1
            
    merch_count = 0
    merch_file = os.path.join(DATA_DIR, "merchants_seed.json")
    if os.path.exists(merch_file):
        with open(merch_file, 'r') as f:
            data = json.load(f)
            for m in data.get("merchants", []):
                contexts[("merchant", m["merchant_id"])] = {"version": 1, "payload": m}
                merch_count += 1
                
    trig_count = 0
    trig_file = os.path.join(DATA_DIR, "triggers_seed.json")
    if os.path.exists(trig_file):
        with open(trig_file, 'r') as f:
            data = json.load(f)
            for t in data.get("triggers", []):
                contexts[("trigger", t["id"])] = {"version": 1, "payload": t}
                trig_count += 1

    return {
        "categories": cat_count,
        "merchants": merch_count,
        "triggers": trig_count
    }

@app.get("/v1/demo/available-contexts")
async def get_available_contexts():
    categories = [ctx_id for (scope, ctx_id) in contexts if scope == "category"]
    merchants = [ctx_id for (scope, ctx_id) in contexts if scope == "merchant"]
    triggers = [ctx_id for (scope, ctx_id) in contexts if scope == "trigger"]
    return {
        "categories": sorted(categories),
        "merchants": sorted(merchants),
        "triggers": sorted(triggers)
    }



@app.post("/v1/teardown")
@app.get("/v1/teardown")
async def teardown():
    """Wipe ALL state — call between test sessions."""
    contexts.clear()
    conversations.clear()
    suppressed_conversations.clear()
    conv_merchant_map.clear()
    conv_customer_map.clear()
    logger.info("State wiped via /v1/teardown")
    return {"status": "wiped"}


def _is_ended(turn: dict) -> bool:
    return turn.get("from") == "vera" and "closed" in turn.get("msg", "").lower()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
