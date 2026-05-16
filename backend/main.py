import os
import json
import asyncio
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=False), override=True)

from clients import CLIENTS
from market_data import get_market_data, get_market_narrative
from ai_narrative import generate_client_brief
from video_generator import generate_video

app = FastAPI(title="AI Wealth Management Advisor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track video generation jobs
video_jobs = {}

BASE_DIR     = os.path.dirname(__file__)
VIDEOS_DIR   = os.path.join(BASE_DIR, "..", "videos")
CACHE_DIR    = os.path.join(BASE_DIR, "..", "cache")
FEEDBACK_DIR = os.path.join(BASE_DIR, "..", "feedback")
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

os.makedirs(VIDEOS_DIR,   exist_ok=True)
os.makedirs(CACHE_DIR,    exist_ok=True)
os.makedirs(FEEDBACK_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.mount("/videos", StaticFiles(directory=VIDEOS_DIR),   name="videos")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _feedback_path(client_id: str) -> str:
    return os.path.join(FEEDBACK_DIR, f"feedback_{client_id}.json")

def _load_feedback(client_id: str) -> dict | None:
    path = _feedback_path(client_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _cache_path(client_id: str) -> str:
    return os.path.join(CACHE_DIR, f"brief_{client_id}.json")

def _load_cache(client_id: str) -> dict | None:
    """Return cached brief dict if it exists and is < 24 h old, else None."""
    path = _cache_path(client_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        generated_at = datetime.fromisoformat(data["generated_at"])
        age_seconds  = (datetime.now() - generated_at).total_seconds()
        if age_seconds > 86400:   # older than 24 h
            return None
        data["cached"]     = True
        data["age_seconds"] = int(age_seconds)
        return data
    except Exception:
        return None

def _save_cache(client_id: str, payload: dict):
    try:
        with open(_cache_path(client_id), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/api/clients")
async def list_clients():
    summary = []
    for c in CLIENTS:
        summary.append({
            "id": c["id"],
            "name": c["name"],
            "age": c["age"],
            "occupation": c["occupation"],
            "location": c["location"],
            "aum": c["aum"],
            "risk_profile": c["risk_profile"],
            "risk_score": c["risk_score"],
            "ytd_return": c["ytd_return"],
            "benchmark_return": c["benchmark_return"],
            "avatar_initials": c["avatar_initials"],
            "avatar_color": c["avatar_color"],
            "marital_status": c["marital_status"],
            "dependents": c["dependents"],
            "last_meeting": c.get("last_meeting", "N/A")
        })
    return summary


@app.get("/api/clients/{client_id}")
async def get_client(client_id: str):
    client = next((c for c in CLIENTS if c["id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@app.get("/api/market")
def market_data():
    try:
        data = get_market_data()
        narrative = get_market_narrative(data)
        return {"factors": data, "narrative": narrative}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Brief: check cache ─────────────────────────────────────────────────────────

@app.get("/api/brief/{client_id}/cached")
async def get_cached_brief(client_id: str):
    """Return cached brief if < 24 h old, or {cached: false}."""
    cached = _load_cache(client_id)
    if cached:
        return cached
    return {"cached": False}


# ── Brief: generate (and save to cache) ───────────────────────────────────────

@app.post("/api/brief/{client_id}")
async def generate_brief(client_id: str):
    client = next((c for c in CLIENTS if c["id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set. Please add it to your .env file.")

    try:
        market    = get_market_data()
        narrative = get_market_narrative(market)
        feedback  = _load_feedback(client_id)
        brief = await asyncio.to_thread(generate_client_brief, client, market, narrative, feedback)

        # Invalidate any existing video so the brief and video stay in sync
        old_video = os.path.join(VIDEOS_DIR, f"client_{client_id}.mp4")
        if os.path.exists(old_video):
            os.remove(old_video)
        video_jobs.pop(client_id, None)

        result = {
            "client_id":        client_id,
            "client_name":      client["name"],
            "brief":            brief,
            "market_data":      market,
            "market_narrative": narrative,
            "generated_at":     datetime.now().isoformat(),
            "cached":           False,
            "feedback_used":    feedback is not None,
        }
        _save_cache(client_id, result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Feedback ──────────────────────────────────────────────────────────────────

@app.get("/api/feedback/{client_id}")
async def get_feedback(client_id: str):
    feedback = _load_feedback(client_id)
    if feedback:
        return feedback
    return {"exists": False}

@app.post("/api/feedback/{client_id}")
async def save_feedback(client_id: str, payload: dict):
    client = next((c for c in CLIENTS if c["id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    payload["client_id"]    = client_id
    payload["submitted_at"] = datetime.now().isoformat()
    try:
        with open(_feedback_path(client_id), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return {"success": True, "message": "Feedback saved. It will be incorporated in the next brief."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Video generation ───────────────────────────────────────────────────────────

def _run_video_generation(client_id: str, client: dict, market: dict, brief: dict):
    try:
        video_jobs[client_id] = {"status": "generating", "progress": "Generating narration & slides…"}
        output_path = os.path.join(VIDEOS_DIR, f"client_{client_id}.mp4")
        if os.path.exists(output_path):
            os.remove(output_path)
        generate_video(client, market, brief, output_path)
        video_jobs[client_id] = {
            "status":   "ready",
            "url":      f"/videos/client_{client_id}.mp4",
            "filename": f"{client['name'].replace(' ', '_')}_Brief.mp4"
        }
    except Exception as e:
        video_jobs[client_id] = {"status": "error", "detail": str(e)}


@app.post("/api/video/{client_id}")
async def start_video_generation(client_id: str, background_tasks: BackgroundTasks, payload: dict = {}):
    client = next((c for c in CLIENTS if c["id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    brief  = payload.get("brief", {})
    market = payload.get("market_data", {})

    if not brief:
        raise HTTPException(status_code=400, detail="Brief data required. Generate brief first.")

    video_jobs[client_id] = {"status": "queued"}
    background_tasks.add_task(_run_video_generation, client_id, client, market, brief)

    return {"job_id": client_id, "status": "queued", "message": "Video generation started"}


@app.get("/api/video/{client_id}/exists")
async def video_exists(client_id: str):
    """Check if a video file already exists on disk (survives server restarts)."""
    video_path = os.path.join(VIDEOS_DIR, f"client_{client_id}.mp4")
    if os.path.exists(video_path) and os.path.getsize(video_path) > 10000:
        return {"exists": True, "url": f"/videos/client_{client_id}.mp4"}
    return {"exists": False}


@app.get("/api/video/{client_id}/status")
async def video_status(client_id: str):
    return video_jobs.get(client_id, {"status": "not_started"})


@app.get("/api/video/{client_id}/file")
async def get_video_file(client_id: str):
    video_path = os.path.join(VIDEOS_DIR, f"client_{client_id}.mp4")
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not generated yet")
    return FileResponse(video_path, media_type="video/mp4",
                        filename=f"Client_{client_id}_Brief.mp4")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
