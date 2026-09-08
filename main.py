"""
Serves the Likeness Watch agent over HTTP for Cloud Run, and exposes:
  - POST /report            legacy single-talent endpoint (curl/tests)
  - POST /report/stream     roster mode: streams each finished case file back
  - POST /watchlist         (auth required) add a talent to your watchlist
  - GET  /watchlist         (auth required) list your watchlist
  - DELETE /watchlist/{id}  (auth required) remove a watchlist entry
  - POST /cron/recheck      (cron-secret protected) re-checks every watched
                              talent across every user, emails on new activity
"""

import asyncio
import json
import os
import uuid

import uvicorn
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from likeness_watch_agent.agent import root_agent
from likeness_watch_agent.auth import verify_google_token
from likeness_watch_agent import store
from likeness_watch_agent.notify import send_alert_email

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "likeness_watch_agent"
CRON_SECRET = os.environ.get("CRON_SECRET")

app: FastAPI = get_fast_api_app(agents_dir=AGENT_DIR, web=False)

_session_service = InMemorySessionService()
_runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=_session_service)

MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 10


class TalentInput(BaseModel):
    talent_name: str
    known_endorsements: list[str] = []


class ReportRequest(TalentInput):
    pass


class RosterRequest(BaseModel):
    talents: list[TalentInput]


def _require_user(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Google Sign-In token")
    token = authorization.removeprefix("Bearer ").strip()
    user = verify_google_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired sign-in token")
    return user


async def _run_single_report(talent: TalentInput) -> dict:
    """Runs the agent end-to-end for one talent and returns the validated
    RiskReport JSON, retrying on transient errors like Gemini's occasional
    503 'high demand' response."""
    last_error = "unknown error"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        user_id = f"demo-{uuid.uuid4().hex[:8]}"
        session = await _session_service.create_session(app_name=APP_NAME, user_id=user_id)

        message = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=(
                f"Monitor {talent.talent_name}. Known real endorsements: "
                f"{', '.join(talent.known_endorsements) or 'none provided'}."
            ))],
        )

        try:
            report_json = None
            async for event in _runner.run_async(user_id=user_id, session_id=session.id, new_message=message):
                for part in getattr(event.content, "parts", []) or []:
                    fr = getattr(part, "function_response", None)
                    if fr and fr.name == "compile_final_report":
                        report_json = fr.response

            if report_json is not None:
                return report_json
            last_error = "Agent did not produce a final report"

        except Exception as e:
            last_error = str(e)

        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(RETRY_DELAY_SECONDS)

    return {"talent_name": talent.talent_name, "error": f"Failed after {MAX_ATTEMPTS} attempts: {last_error}"}


@app.post("/report")
async def generate_report(req: ReportRequest):
    result = await _run_single_report(TalentInput(**req.model_dump()))
    if "error" in result:
        return JSONResponse(status_code=502, content=result)
    return result


@app.post("/report/stream")
async def generate_roster_stream(req: RosterRequest):
    async def _stream():
        for talent in req.talents:
            result = await _run_single_report(talent)
            yield json.dumps(result) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@app.post("/auth/session")
async def create_session_from_token(authorization: str | None = Header(default=None)):
    """Called right after Google Sign-In succeeds client-side, to register
    the user in Firestore so the cron job knows where to email alerts."""
    user = _require_user(authorization)
    store.upsert_user(user["uid"], user["email"], user["name"])
    return {"email": user["email"], "name": user["name"]}


@app.post("/watchlist")
async def add_watchlist_entry(talent: TalentInput, authorization: str | None = Header(default=None)):
    user = _require_user(authorization)
    doc_id = store.add_to_watchlist(user["uid"], talent.talent_name, talent.known_endorsements)
    return {"id": doc_id}


@app.get("/watchlist")
async def get_watchlist(authorization: str | None = Header(default=None)):
    user = _require_user(authorization)
    return store.list_watchlist(user["uid"])


@app.delete("/watchlist/{doc_id}")
async def delete_watchlist_entry(doc_id: str, authorization: str | None = Header(default=None)):
    user = _require_user(authorization)
    store.remove_from_watchlist(user["uid"], doc_id)
    return {"deleted": doc_id}


@app.post("/cron/recheck")
async def cron_recheck(x_cron_secret: str | None = Header(default=None)):
    """Re-checks every watched talent across every user. Triggered by Cloud
    Scheduler on a schedule, protected by a shared secret header rather than
    a full user login since it's a machine-to-machine call."""
    if not CRON_SECRET or x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=403, detail="Invalid cron secret")

    checked, alerted = 0, 0
    for uid, doc_id, entry in store.iter_all_watchlist_entries():
        talent = TalentInput(
            talent_name=entry["talent_name"],
            known_endorsements=entry.get("known_endorsements", []),
        )
        result = await _run_single_report(talent)
        checked += 1
        if "error" in result:
            continue

        new_urls = sorted({f["source"]["url"] for f in result.get("findings", [])})
        old_urls = sorted(entry.get("last_finding_urls", []))
        flag_escalated = _flag_rank(result["risk_flag"]) > _flag_rank(entry.get("last_risk_flag"))

        if new_urls != old_urls or flag_escalated:
            email = store.get_user_email(uid)
            if email:
                sent = send_alert_email(
                    email, result["talent_name"], result["risk_flag"],
                    result["reason"], result["recommended_action"],
                )
                if sent:
                    alerted += 1

        store.update_watchlist_state(uid, doc_id, result["risk_flag"], new_urls)

    return {"checked": checked, "alerted": alerted}


def _flag_rank(flag: str | None) -> int:
    return {"green": 0, "yellow": 1, "red": 2}.get(flag, -1)


@app.get("/", include_in_schema=False)
async def serve_index():
    """Serves index.html with the OAuth Client ID injected server-side —
    keeps the real client ID out of the source file and lets it be set purely
    via environment variable, same as any other credential in this project."""
    path = os.path.join(AGENT_DIR, "static", "index.html")
    with open(path, "r") as f:
        html = f.read()
    html = html.replace("%%GOOGLE_OAUTH_CLIENT_ID%%", os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""))
    return HTMLResponse(html)


app.mount("/static", StaticFiles(directory=os.path.join(AGENT_DIR, "static")), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
