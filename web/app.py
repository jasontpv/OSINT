"""
OSINT Web UI — FastAPI application.
Run with:  python -m web.app
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import hashlib
import hmac
import secrets

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware
from sse_starlette.sse import EventSourceResponse

# Ensure project root is on sys.path so pipeline modules resolve
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from web.database import (
    add_facts_to_cluster,
    blacklist_ip,
    create_cluster,
    create_investigation,
    delete_cluster,
    delete_investigation,
    get_activity_actions,
    get_activity_countries,
    get_activity_logs,
    get_activity_sessions,
    get_blacklist,
    get_cluster,
    get_cluster_count,
    get_cluster_facts,
    get_clusters,
    get_dashboard_stats,
    get_fact,
    get_fact_types,
    get_facts,
    get_investigation,
    get_login_logs,
    get_reports,
    get_unclustered_facts,
    init_db,
    insert_facts,
    insert_report,
    is_ip_blacklisted,
    list_investigations,
    log_activity,
    log_login,
    log_logout,
    remove_fact_from_cluster,
    unblacklist_ip,
    update_cluster,
    update_fact,
    update_investigation,
)

logger = logging.getLogger("osint_web")
logging.basicConfig(level=logging.INFO)

REPORTS_DIR = PROJECT_ROOT / "OSINT_WORKSPACE" / "data" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── SSE event buses (one asyncio.Queue per investigation) ───────────
_event_queues: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)


def _push_event(inv_id: str, stage: str, status: str, message: str = "", **extra):
    q = _event_queues[inv_id]
    payload = {"stage": stage, "status": status, "message": message, "ts": datetime.utcnow().isoformat(), **extra}
    q.put_nowait(json.dumps(payload))


# ── Available tools registry ────────────────────────────────────────

TOOLS = [
    {"id": "serper", "name": "Serper Google Search", "env_key": "SERPER_API_KEY", "default": True, "type": "api"},
    {"id": "scrapingant", "name": "ScrapingAnt Scraper", "env_key": "SCRAPINGANT_API_KEY", "default": True, "type": "api"},
    {"id": "shodan", "name": "Shodan", "env_key": "SHODAN_API_KEY", "default": False, "type": "api"},
    {"id": "spiderfoot", "name": "SpiderFoot", "env_key": "SPIDERFOOT_API_KEY", "default": False, "type": "api"},
    {"id": "builtwith", "name": "BuiltWith", "env_key": "BUILTWITH_API_KEY", "default": False, "type": "api"},
    {"id": "nmap", "name": "Nmap Scan", "env_key": None, "default": False, "type": "cli", "cmd": "nmap"},
    {"id": "whois", "name": "Whois Lookup", "env_key": None, "default": False, "type": "cli", "cmd": "whois"},
    {"id": "theharvester", "name": "theHarvester", "env_key": None, "default": False, "type": "cli", "cmd": "theHarvester"},
    {"id": "photon", "name": "Photon Crawler", "env_key": None, "default": False, "type": "cli", "cmd": "photon"},
]


def _tool_available(tool: Dict) -> bool:
    if tool["type"] == "api":
        return bool(os.getenv(tool["env_key"], ""))
    return shutil.which(tool.get("cmd", "")) is not None


# ── Auth ─────────────────────────────────────────────────────────────

APP_PASSWORD = os.getenv("OSINT_PASSWORD", "mwxosint")
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_hex(32))
SESSION_COOKIE = "osint_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

_signer = URLSafeTimedSerializer(SESSION_SECRET)

PUBLIC_PATHS = {"/login", "/static"}


def _is_authenticated(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        return False
    try:
        data = _signer.loads(token, max_age=SESSION_MAX_AGE)
        return data.get("auth") is True
    except Exception:
        return False


# ── IP geolocation cache ────────────────────────────────────────────

_geo_cache: Dict[str, Dict] = {}


async def _geolocate(ip: str) -> Dict:
    if ip in _geo_cache:
        return _geo_cache[ip]
    if ip in ("127.0.0.1", "::1", "localhost", "unknown") or ip.startswith("10.") or ip.startswith("192.168."):
        result = {"city": "Local", "regionName": "", "country": "Local", "lat": 0, "lon": 0}
        _geo_cache[ip] = result
        return result
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"http://ip-api.com/json/{ip}?fields=city,regionName,country,lat,lon")
            if r.status_code == 200:
                data = r.json()
                _geo_cache[ip] = data
                return data
    except Exception:
        pass
    empty = {"city": "", "regionName": "", "country": "", "lat": 0, "lon": 0}
    _geo_cache[ip] = empty
    return empty


def _get_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else "unknown"
    )


def _get_session_short(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE, "")
    return token[:16] if token else ""


SKIP_LOG_PREFIXES = ("/static", "/favicon")

_blacklist_set: set = set()


async def _load_blacklist():
    global _blacklist_set
    bl = await get_blacklist()
    _blacklist_set = {entry["ip"] for entry in bl}


def _action_from_path(method: str, path: str) -> str:
    if path == "/login" and method == "POST":
        return "login_attempt"
    if path == "/login":
        return "login_page"
    if path == "/logout":
        return "logout"
    if path == "/":
        return "dashboard"
    if path == "/investigate" and method == "POST":
        return "start_investigation"
    if path.startswith("/investigate"):
        return "investigate"
    if path == "/reports" or (path.startswith("/reports") and "/triage" not in path and len(path.split("/")) == 3):
        return "view_report"
    if "/triage" in path:
        return "triage"
    if path.startswith("/reports"):
        return "reports_list"
    if path == "/settings" and method == "POST":
        return "save_settings"
    if path == "/settings":
        return "settings"
    if path == "/log":
        return "view_log"
    if path.startswith("/api/blacklist"):
        if method == "POST":
            return "admin:ban_ip"
        if method == "DELETE":
            return "admin:unban_ip"
    if path.startswith("/api/"):
        return f"api:{path.split('/')[2]}" if len(path.split("/")) > 2 else "api"
    return "page_view"


_BANNED_MESSAGES = [
    "Nice try. We see you.",
    "This IP has been permanently banned. Have a great day.",
    "Access denied. Your activity has been logged and reported.",
    "You've been blacklisted. Maybe try a different hobby?",
    "403 — Forbidden. Yes, we mean you specifically.",
    "Our OSINT tools work both ways. We know where you are.",
    "Knock knock. Nobody's home. Especially not for you.",
    "All your requests are belong to us.",
    "Roses are red, violets are blue, you're banned from this server, and we're watching you.",
    "Error 403: Talent not found.",
    "You must be lost. This isn't the server you're looking for.",
    "Blocked. Logged. Geolocated. Anything else?",
    "Imagine thinking a banned IP would just... work.",
    "We appreciate your persistence. The answer is still no.",
    "Your IP has been added to our permanent collection. Thanks for visiting.",
]


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        ip = _get_ip(request)
        if ip in _blacklist_set:
            import random
            msg = random.choice(_BANNED_MESSAGES)
            asyncio.ensure_future(log_activity(
                ip=ip, action="blocked", path=path, method=request.method,
                user_agent=request.headers.get("user-agent", ""), status_code=403,
                detail=msg,
            ))
            return HTMLResponse(
                f"""<!DOCTYPE html><html><head><title>403</title>
<style>body{{background:#0a0a0a;color:#ef4444;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}}
.box{{max-width:500px;padding:40px}}.code{{font-size:72px;font-weight:bold;opacity:.3}}.msg{{font-size:18px;margin-top:20px;line-height:1.6}}</style></head>
<body><div class="box"><div class="code">403</div><div class="msg">{msg}</div></div></body></html>""",
                status_code=403,
            )

        if any(path.startswith(p) for p in SKIP_LOG_PREFIXES):
            return await call_next(request)

        if any(path.startswith(p) for p in PUBLIC_PATHS):
            response = await call_next(request)
            if path != "/login" or request.method == "GET":
                asyncio.ensure_future(self._log_request(request, response.status_code))
            return response

        if _is_authenticated(request):
            response = await call_next(request)
            asyncio.ensure_future(self._log_request(request, response.status_code))
            return response

        if path.startswith("/api/"):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return RedirectResponse("/login", status_code=303)

    @staticmethod
    async def _log_request(request: Request, status_code: int):
        try:
            ip = _get_ip(request)
            geo = await _geolocate(ip)
            await log_activity(
                ip=ip,
                action=_action_from_path(request.method, request.url.path),
                path=request.url.path,
                method=request.method,
                session_token=_get_session_short(request),
                user_agent=request.headers.get("user-agent", ""),
                status_code=status_code,
                geo_city=geo.get("city", ""),
                geo_region=geo.get("regionName", ""),
                geo_country=geo.get("country", ""),
                geo_lat=geo.get("lat", 0),
                geo_lon=geo.get("lon", 0),
            )
        except Exception:
            pass


# ── FastAPI application ─────────────────────────────────────────────

app = FastAPI(title="OSINT Kanban Pipeline")
app.add_middleware(AuthMiddleware)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def startup():
    await init_db()
    await _load_blacklist()


# ── Auth routes ─────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "login.html", context={"error": error})


@app.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    ua = request.headers.get("user-agent", "")

    if hmac.compare_digest(password, APP_PASSWORD):
        token = _signer.dumps({"auth": True})
        await log_login(ip, ua, success=True, session_token=token[:32])
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
        return response

    await log_login(ip, ua, success=False)
    return templates.TemplateResponse(request, "login.html", context={
        "error": "Invalid password",
    })


@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        await log_logout(token[:32])
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


# ── Page routes ─────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    stats = await get_dashboard_stats()
    investigations = await list_investigations(limit=10)
    return templates.TemplateResponse(request, "dashboard.html", context={
        "stats": stats,
        "investigations": investigations,
    })


@app.get("/investigate", response_class=HTMLResponse)
async def investigate_page(request: Request):
    tools_with_status = [
        {**t, "available": _tool_available(t)} for t in TOOLS
    ]
    return templates.TemplateResponse(request, "investigate.html", context={
        "tools": tools_with_status,
    })


@app.get("/investigate/{inv_id}/progress", response_class=HTMLResponse)
async def progress_page(request: Request, inv_id: str):
    inv = await get_investigation(inv_id)
    if not inv:
        return RedirectResponse("/")
    return templates.TemplateResponse(request, "progress.html", context={
        "investigation": inv,
    })


@app.get("/reports", response_class=HTMLResponse)
async def reports_list_page(request: Request, search: str = "", target_type: str = "", status: str = ""):
    investigations = await list_investigations(limit=100, search=search)
    if target_type:
        investigations = [i for i in investigations if i["target_type"] == target_type]
    if status:
        investigations = [i for i in investigations if i["status"] == status]
    for inv in investigations:
        inv["cluster_count"] = await get_cluster_count(inv["id"])
    return templates.TemplateResponse(request, "reports.html", context={
        "investigations": investigations,
        "search": search,
        "target_type": target_type,
        "status_filter": status,
    })


@app.get("/reports/{inv_id}", response_class=HTMLResponse)
async def report_detail_page(request: Request, inv_id: str, fact_type: str = "", sort: str = "confidence", order: str = "desc"):
    inv = await get_investigation(inv_id)
    if not inv:
        return RedirectResponse("/reports")
    facts = await get_facts(inv_id, fact_type=fact_type, sort_by=sort, order=order)
    fact_types = await get_fact_types(inv_id)
    reports = await get_reports(inv_id)

    confidence_buckets = {"high": 0, "medium": 0, "low": 0}
    for f in facts:
        c = f["confidence"]
        if c >= 80:
            confidence_buckets["high"] += 1
        elif c >= 50:
            confidence_buckets["medium"] += 1
        else:
            confidence_buckets["low"] += 1

    cluster_count = await get_cluster_count(inv_id)

    parent_inv = None
    parent_cluster_id = inv.get("parent_cluster_id")
    if parent_cluster_id:
        parent_cluster = await get_cluster(parent_cluster_id)
        if parent_cluster:
            parent_inv = await get_investigation(parent_cluster["investigation_id"])

    return templates.TemplateResponse(request, "report.html", context={
        "investigation": inv,
        "facts": facts,
        "fact_types": fact_types,
        "reports": reports,
        "confidence_buckets": confidence_buckets,
        "current_type": fact_type,
        "current_sort": sort,
        "current_order": order,
        "cluster_count": cluster_count,
        "parent_investigation": parent_inv,
    })


@app.get("/reports/{inv_id}/triage", response_class=HTMLResponse)
async def triage_page(request: Request, inv_id: str):
    inv = await get_investigation(inv_id)
    if not inv:
        return RedirectResponse("/reports")
    clusters = await get_clusters(inv_id)
    all_facts = await get_facts(inv_id)
    unclustered = await get_unclustered_facts(inv_id)
    fact_types = await get_fact_types(inv_id)

    cluster_facts_map = {}
    for cluster in clusters:
        cfacts = await get_cluster_facts(cluster["id"])
        for f in cfacts:
            cluster_facts_map[str(f["id"])] = cluster["id"]

    return templates.TemplateResponse(request, "triage.html", context={
        "investigation": inv,
        "clusters": clusters,
        "all_facts": all_facts,
        "unclustered_facts": unclustered,
        "fact_types": fact_types,
        "cluster_facts_map": cluster_facts_map,
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    tools_status = []
    for t in TOOLS:
        status = "available" if _tool_available(t) else "not_configured"
        key_val = ""
        if t["env_key"]:
            raw = os.getenv(t["env_key"], "")
            key_val = f"{raw[:6]}{'*' * max(0, len(raw) - 6)}" if raw else ""
        tools_status.append({**t, "status": status, "key_masked": key_val})
    return templates.TemplateResponse(request, "settings.html", context={
        "tools": tools_status,
    })


# ── Hidden log page (not in nav) ────────────────────────────────────

@app.get("/log", response_class=HTMLResponse)
async def activity_log_page(
    request: Request,
    action: str = "",
    ip: str = "",
    session: str = "",
    country: str = "",
):
    logs = await get_activity_logs(limit=500, action=action, ip=ip, session=session, country=country)
    actions = await get_activity_actions()
    countries = await get_activity_countries()
    sessions = await get_activity_sessions()
    bl = await get_blacklist()
    return templates.TemplateResponse(request, "log.html", context={
        "logs": logs,
        "actions": actions,
        "countries": countries,
        "sessions": sessions,
        "blacklist": bl,
        "blacklist_ips": {entry["ip"] for entry in bl},
        "f_action": action,
        "f_ip": ip,
        "f_session": session,
        "f_country": country,
    })


@app.post("/api/blacklist")
async def api_ban_ip(request: Request):
    body = await request.json()
    ip = body.get("ip", "").strip()
    reason = body.get("reason", "")
    geo_city = body.get("geo_city", "")
    geo_country = body.get("geo_country", "")
    if not ip:
        return JSONResponse({"error": "ip required"}, status_code=400)
    await blacklist_ip(ip, reason=reason, geo_city=geo_city, geo_country=geo_country)
    _blacklist_set.add(ip)
    return JSONResponse({"ok": True, "ip": ip})


@app.delete("/api/blacklist/{ip:path}")
async def api_unban_ip(ip: str):
    await unblacklist_ip(ip)
    _blacklist_set.discard(ip)
    return JSONResponse({"ok": True, "ip": ip})


# ── API routes ──────────────────────────────────────────────────────

@app.post("/api/investigate")
async def start_investigation(
    target: str = Form(...),
    target_type: str = Form("person"),
    tools: List[str] = Form(default=[]),
    formats: List[str] = Form(default=["json"]),
    wip_recon: int = Form(3),
    wip_harvesting: int = Form(5),
    wip_analyst: int = Form(2),
    wip_scribe: int = Form(1),
    max_retries: int = Form(3),
    privacy_mode: str = Form("local"),
):
    inv_id = uuid.uuid4().hex[:12]
    config = {
        "wip_limits": {"RECON": wip_recon, "HARVESTING": wip_harvesting, "ANALYST": wip_analyst, "SCRIBE": wip_scribe},
        "max_retries": max_retries,
        "privacy_mode": privacy_mode,
    }
    await create_investigation(inv_id, target, target_type, tools, formats, config)
    asyncio.create_task(_run_pipeline(inv_id, target, target_type, tools, formats, config))
    return RedirectResponse(f"/investigate/{inv_id}/progress", status_code=303)


@app.get("/api/investigate/{inv_id}/stream")
async def sse_stream(inv_id: str):
    async def event_generator():
        q = _event_queues[inv_id]
        while True:
            try:
                data = await asyncio.wait_for(q.get(), timeout=120)
                yield {"event": "update", "data": data}
                parsed = json.loads(data)
                if parsed.get("status") in ("completed", "failed"):
                    yield {"event": "done", "data": data}
                    break
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": "{}"}

    return EventSourceResponse(event_generator())


@app.delete("/api/reports/{inv_id}")
async def api_delete_investigation(inv_id: str):
    reports = await get_reports(inv_id)
    for r in reports:
        p = Path(r["file_path"])
        if p.exists():
            p.unlink()
    await delete_investigation(inv_id)
    return JSONResponse({"ok": True})


@app.get("/api/reports/{inv_id}/download/{fmt}")
async def download_report(inv_id: str, fmt: str):
    reports = await get_reports(inv_id)
    for r in reports:
        if r["format"] == fmt and Path(r["file_path"]).exists():
            return FileResponse(r["file_path"], filename=Path(r["file_path"]).name)
    return JSONResponse({"error": "Report not found"}, status_code=404)


@app.post("/api/settings/keys")
async def save_api_keys(request: Request):
    form = await request.form()
    env_path = PROJECT_ROOT / ".env"
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    env_dict = {}
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env_dict[k.strip()] = v.strip()
        else:
            env_dict[f"__comment_{len(env_dict)}"] = line

    for key in form:
        val = form[key].strip()
        if val:
            env_dict[key] = val
            os.environ[key] = val

    new_lines = []
    for k, v in env_dict.items():
        if k.startswith("__comment_"):
            new_lines.append(v)
        else:
            new_lines.append(f"{k}={v}")
    env_path.write_text("\n".join(new_lines) + "\n")

    return RedirectResponse("/settings", status_code=303)


# ── Cluster API routes ──────────────────────────────────────────────

@app.post("/api/clusters")
async def api_create_cluster(request: Request):
    body = await request.json()
    investigation_id = body.get("investigation_id")
    label = body.get("label", "").strip()
    notes = body.get("notes", "")
    if not investigation_id or not label:
        return JSONResponse({"error": "investigation_id and label are required"}, status_code=400)
    cluster_id = uuid.uuid4().hex[:12]
    cluster = await create_cluster(cluster_id, investigation_id, label, notes)
    return JSONResponse(cluster)


@app.put("/api/clusters/{cluster_id}")
async def api_update_cluster(cluster_id: str, request: Request):
    body = await request.json()
    updates = {}
    if "label" in body:
        updates["label"] = body["label"].strip()
    if "notes" in body:
        updates["notes"] = body["notes"]
    if not updates:
        return JSONResponse({"error": "Nothing to update"}, status_code=400)
    await update_cluster(cluster_id, **updates)
    return JSONResponse({"ok": True})


@app.delete("/api/clusters/{cluster_id}")
async def api_delete_cluster(cluster_id: str):
    await delete_cluster(cluster_id)
    return JSONResponse({"ok": True})


@app.post("/api/clusters/{cluster_id}/facts")
async def api_add_facts_to_cluster(cluster_id: str, request: Request):
    body = await request.json()
    fact_ids = body.get("fact_ids", [])
    if not fact_ids:
        return JSONResponse({"error": "fact_ids required"}, status_code=400)
    added = await add_facts_to_cluster(cluster_id, fact_ids)
    return JSONResponse({"added": added})


@app.delete("/api/clusters/{cluster_id}/facts/{fact_id}")
async def api_remove_fact_from_cluster(cluster_id: str, fact_id: int):
    await remove_fact_from_cluster(cluster_id, fact_id)
    return JSONResponse({"ok": True})


@app.get("/api/clusters/{cluster_id}/facts")
async def api_get_cluster_facts(cluster_id: str):
    facts = await get_cluster_facts(cluster_id)
    return JSONResponse(facts)


@app.get("/api/clusters/{cluster_id}/pivot-query")
async def api_pivot_query(cluster_id: str):
    from osint_recon_stage import build_pivot_query
    facts = await get_cluster_facts(cluster_id)
    pivot = build_pivot_query(facts)
    return JSONResponse(pivot)


@app.post("/api/clusters/{cluster_id}/pivot")
async def api_pivot_from_cluster(cluster_id: str, request: Request):
    """Launch a new investigation seeded from a cluster's pivot query."""
    body = await request.json()
    query = body.get("query", "").strip()
    target_type = body.get("target_type", "person")
    if not query:
        return JSONResponse({"error": "query is required"}, status_code=400)

    cluster = await get_cluster(cluster_id)
    if not cluster:
        return JSONResponse({"error": "Cluster not found"}, status_code=404)

    inv_id = uuid.uuid4().hex[:12]
    config = {
        "wip_limits": {"RECON": 3, "HARVESTING": 5, "ANALYST": 2, "SCRIBE": 1},
        "max_retries": 3,
        "privacy_mode": "local",
    }
    await create_investigation(inv_id, query, target_type, [], ["json", "html", "pdf"], config)
    await update_investigation(inv_id, parent_cluster_id=cluster_id)

    asyncio.create_task(_run_pipeline(inv_id, query, target_type, [], ["json", "html", "pdf"], config))
    return JSONResponse({"investigation_id": inv_id, "redirect": f"/investigate/{inv_id}/progress"})


# ── Fact management ─────────────────────────────────────────────────

@app.delete("/api/facts/{fact_id}")
async def api_delete_fact(fact_id: int):
    from web.database import delete_fact
    await delete_fact(fact_id)
    return JSONResponse({"ok": True})


# ── On-demand scraping ──────────────────────────────────────────────

@app.post("/api/facts/{fact_id}/scrape")
async def api_scrape_fact(fact_id: int):
    """Scrape the URL from a web_reference fact and extract structured data."""
    fact = await get_fact(fact_id)
    if not fact:
        return JSONResponse({"error": "Fact not found"}, status_code=404)
    if fact["fact_type"] != "web_reference":
        return JSONResponse({"error": "Only web_reference facts can be scraped"}, status_code=400)

    ctx = json.loads(fact.get("context_json", "{}") or "{}")
    if ctx.get("scraped"):
        return JSONResponse({"error": "Already scraped", "scraped_at": ctx.get("scraped_at")}, status_code=409)

    api_key = os.getenv("SCRAPINGANT_API_KEY", "")
    if not api_key:
        return JSONResponse({"error": "SCRAPINGANT_API_KEY not configured"}, status_code=503)

    from osint_harvesting_stage import ScrapingantClientV2
    from osint_content_parser import parse_scraped_html

    client = ScrapingantClientV2(api_key)
    try:
        scraped = await client.scrape_url(fact["value"])
    except Exception as e:
        return JSONResponse({"error": f"Scrape failed: {e}"}, status_code=502)

    if scraped.get("status_code", 0) != 200:
        return JSONResponse({"error": f"Scrape failed with status {scraped.get('status_code')}"}, status_code=502)

    # v2 API returns plain text; older clients returned HTML. Use whichever we got.
    content = scraped.get("html_content") or scraped.get("text_content") or ""
    new_facts = parse_scraped_html(fact["value"], content)

    if new_facts:
        await insert_facts(fact["investigation_id"], new_facts)

    ctx["scraped"] = True
    ctx["scraped_at"] = datetime.utcnow().isoformat()
    ctx["facts_extracted"] = len(new_facts)
    await update_fact(fact_id, context_json=json.dumps(ctx))

    inv = await get_investigation(fact["investigation_id"])
    if inv:
        new_count = (inv.get("fact_count") or 0) + len(new_facts)
        await update_investigation(fact["investigation_id"], fact_count=new_count)

    return JSONResponse({
        "ok": True,
        "facts_extracted": len(new_facts),
        "new_facts": new_facts,
    })


# ── Pipeline runner ─────────────────────────────────────────────────

def _analyst_facts_to_web_shape(raw_facts: List[Dict]) -> List[Dict]:
    """Translate AnalysisReport.facts dicts into the shape insert_facts() expects.

    Backend facts use ``type``/``confidence`` (0-1 float) with UPPERCASE types;
    the web DB uses ``fact_type``/``confidence_score`` (0-100) with lowercase types.
    """
    out: List[Dict] = []
    for f in raw_facts or []:
        if not isinstance(f, dict):
            continue
        ftype = str(f.get("fact_type") or f.get("type") or "finding").lower()
        value = str(f.get("value") or f.get("text") or "").strip()
        if not value:
            continue
        conf = f.get("confidence_score", f.get("confidence", 0))
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.0
        if conf <= 1.0:
            conf *= 100.0
        sources = f.get("sources") or []
        if isinstance(sources, str):
            sources = [sources]
        out.append({
            "fact_type": ftype,
            "value": value,
            "confidence_score": round(conf, 1),
            "sources": list(sources),
            "context": f.get("metadata") or f.get("context") or {},
        })
    return out


async def _run_pipeline(inv_id: str, target: str, target_type: str, tools: List[str], formats: List[str], config: Dict):
    """Execute the OSINT pipeline in a background task, pushing SSE events."""
    from osint_kanban_manager import OSINTKanbanManager, PipelineConfig

    try:
        report_files_before = set(REPORTS_DIR.iterdir()) if REPORTS_DIR.exists() else set()
        _push_event(inv_id, "pipeline", "started", f"Investigation started for '{target}'")

        fmt_str = "both" if len(formats) > 1 else (formats[0] if formats else "json")
        pipeline_config = PipelineConfig(
            target_name=target,
            target_type=target_type,
            wip_limits=config.get("wip_limits", {"RECON": 3, "HARVESTING": 5, "ANALYST": 2, "SCRIBE": 1}),
            api_keys={
                "SERPER_API_KEY": os.getenv("SERPER_API_KEY", ""),
                "SCRAPINGANT_API_KEY": os.getenv("SCRAPINGANT_API_KEY", ""),
                "SHODAN_API_KEY": os.getenv("SHODAN_API_KEY", ""),
                "PRIVACY_MODE": config.get("privacy_mode", "local"),
            },
            max_retries_per_ticket=config.get("max_retries", 3),
            enable_circuit_breaker=True,
            recovery_time_after_failure=60,
        )

        manager = OSINTKanbanManager(config=pipeline_config)
        # start_pipeline() injects the master ticket into the RECON column;
        # without this execute_pipeline sees empty columns and exits immediately.
        await manager.start_pipeline(target, target_type)

        stages_order = ["RECON", "HARVESTING", "ANALYST", "SCRIBE"]
        stage_messages = {
            "RECON": "Generating search queries and dorks...",
            "HARVESTING": "Executing searches via Serper API...",
            "ANALYST": "Cross-referencing and scoring facts...",
            "SCRIBE": "Generating reports...",
        }

        orig_execute = manager.execute_pipeline

        async def _instrumented_pipeline(*a, **kw):
            import osint_kanban_manager as km
            orig_info = km.logger.info
            current_idx = [0]

            def _hooked_info(msg, *args, **kwargs):
                orig_info(msg, *args, **kwargs)
                if isinstance(msg, str) and "Entering stage:" in msg:
                    for i, s in enumerate(stages_order):
                        if s in msg:
                            current_idx[0] = i
                            _push_event(inv_id, s, "active", stage_messages.get(s, "Processing..."))
                            for j in range(i):
                                _push_event(inv_id, stages_order[j], "done", "Complete")
                            break
                elif isinstance(msg, str) and "✓" in msg:
                    for s in stages_order:
                        if s in msg:
                            _push_event(inv_id, s, "done", msg.strip())
                            break
                elif isinstance(msg, str) and ("failed" in msg.lower() or "✗" in msg):
                    for s in stages_order:
                        if s in msg:
                            _push_event(inv_id, s, "failed", msg.strip())
                            break

            km.logger.info = _hooked_info
            try:
                return await orig_execute(*a, **kw)
            finally:
                km.logger.info = orig_info

        result = await _instrumented_pipeline(
            query=target,
            report_format=fmt_str,
            output_path=str(REPORTS_DIR / f"osint_{target.replace(' ', '_')}_{inv_id}"),
        )

        # Run optional CLI tools
        cli_tools_requested = [t for t in tools if t in ("nmap", "whois", "theharvester", "photon")]
        cli_results = {}
        if cli_tools_requested:
            _push_event(inv_id, "CLI_TOOLS", "active", f"Running CLI tools: {', '.join(cli_tools_requested)}")
            cli_results = await _run_cli_tools(target, cli_tools_requested)
            _push_event(inv_id, "CLI_TOOLS", "done", f"CLI tools completed ({len(cli_results)} results)")

        all_facts: List[Dict] = []
        ticket = getattr(manager, 'last_ticket', None)
        if ticket and ticket.analysis_results is not None:
            raw_facts = getattr(ticket.analysis_results, "facts", None) or []
            all_facts = _analyst_facts_to_web_shape(raw_facts)

        for tool_name, tool_output in cli_results.items():
            parsed = _parse_cli_output(tool_name, tool_output)
            all_facts.extend(parsed)

        await insert_facts(inv_id, all_facts)

        safe_target = target.replace(' ', '_')

        # Find any new files the scribe generated (match by target name in filename)
        all_files_now = set(REPORTS_DIR.iterdir()) if REPORTS_DIR.exists() else set()
        new_files = all_files_now - report_files_before

        # Also scan for files matching the target name created in the last 30 seconds
        import time as _time
        cutoff = _time.time() - 30
        for f in REPORTS_DIR.iterdir():
            if safe_target.lower() in f.name.lower().replace(":", "").replace(" ", "_") and f.stat().st_mtime > cutoff:
                new_files.add(f)

        for f in new_files:
            ext = f.suffix.lstrip(".")
            if ext in ("html", "pdf", "json", "md"):
                already = await get_reports(inv_id)
                if not any(r["file_path"] == str(f) for r in already):
                    await insert_report(inv_id, ext, str(f), f.stat().st_size)

        fact_count = len(all_facts)
        avg_conf = sum(f.get("confidence_score", f.get("confidence", 0)) for f in all_facts) / max(1, fact_count)

        await update_investigation(
            inv_id,
            status="completed",
            completed_at=datetime.utcnow().isoformat(),
            fact_count=fact_count,
            avg_confidence=round(avg_conf, 1),
        )

        _push_event(inv_id, "pipeline", "completed", f"Done — {fact_count} facts found", fact_count=fact_count)

        await manager.cleanup()

    except Exception as e:
        logger.exception(f"Pipeline failed for {inv_id}")
        await update_investigation(inv_id, status="failed", error_message=str(e))
        _push_event(inv_id, "pipeline", "failed", str(e))


def _parse_cli_output(tool_name: str, raw_output: str) -> List[Dict]:
    """Parse raw CLI tool output into structured facts with proper types."""
    import re
    facts = []
    seen = set()

    email_re = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
    ip_re = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
    domain_re = re.compile(r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b')
    url_re = re.compile(r'https?://[^\s<>"\']+')
    phone_re = re.compile(r'[\+]?[\d\s\-\(\)]{10,}')

    skip_domains = {'example.com', 'localhost', 'google.com', 'googleapis.com', 'gstatic.com',
                    'schema.org', 'w3.org', 'xmlns.com', 'purl.org', 'ogp.me'}

    def _add(fact_type, value, confidence=70.0):
        key = (fact_type, value)
        if key not in seen and len(value) > 2:
            seen.add(key)
            facts.append({
                "fact_type": fact_type,
                "value": value.strip(),
                "confidence_score": confidence,
                "sources": [tool_name],
                "context": {"tool": tool_name},
            })

    for url in url_re.findall(raw_output):
        _add("web_reference", url, 75.0)

    for email in email_re.findall(raw_output):
        if not any(email.endswith(f'@{d}') for d in skip_domains):
            _add("email", email.lower(), 80.0)

    for ip in ip_re.findall(raw_output):
        octets = ip.split('.')
        if all(0 <= int(o) <= 255 for o in octets) and ip not in ('0.0.0.0', '127.0.0.1', '255.255.255.255'):
            _add("ip_address", ip, 65.0)

    real_tlds = {'com', 'net', 'org', 'edu', 'gov', 'io', 'co', 'us', 'uk', 'de', 'fr',
                  'ru', 'cn', 'jp', 'au', 'ca', 'br', 'in', 'info', 'biz', 'me', 'tv', 'xyz'}
    for domain in domain_re.findall(raw_output):
        domain_lower = domain.lower()
        tld = domain_lower.rsplit('.', 1)[-1]
        if (tld in real_tlds
                and domain_lower not in skip_domains
                and not ip_re.match(domain_lower)
                and '.' in domain_lower
                and len(domain_lower.split('.')[0]) > 1):
            if not any(domain_lower.endswith(f'.{d}') for d in skip_domains):
                _add("hostname", domain_lower, 60.0)

    if tool_name == "theharvester":
        for line in raw_output.splitlines():
            line = line.strip()
            if line.startswith('[*]') or line.startswith('[-]') or not line:
                continue
            if '@' in line and email_re.search(line):
                continue
            if line and len(line) < 200 and not line.startswith('*'):
                for match in domain_re.findall(line):
                    _add("hostname", match.lower(), 65.0)

    if not facts:
        _add("cli_result", raw_output[:500], 50.0)

    return facts


async def _run_cli_tools(target: str, tool_ids: List[str]) -> Dict[str, str]:
    """Run selected CLI tools and return their output."""
    import subprocess
    results = {}
    tool_cmds = {
        "nmap": ["nmap", "-sV", "--top-ports", "100", target],
        "whois": ["whois", target],
        "theharvester": ["theHarvester", "-d", target, "-b", "all"],
        "photon": ["python", str(PROJECT_ROOT / "OSINT_WORKSPACE" / "tools" / "Photo_s0md3v" / "photon.py"), "-u", target],
    }
    for tool_id in tool_ids:
        cmd = tool_cmds.get(tool_id)
        if not cmd or not shutil.which(cmd[0]):
            results[tool_id] = f"Tool '{tool_id}' not found in PATH"
            continue
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            results[tool_id] = stdout.decode(errors="replace")[:5000]
        except asyncio.TimeoutError:
            results[tool_id] = f"Tool '{tool_id}' timed out after 120s"
        except Exception as e:
            results[tool_id] = f"Error running '{tool_id}': {e}"
    return results


# ── Entrypoint ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)
