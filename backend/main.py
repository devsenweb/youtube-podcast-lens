from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import requests
import os
# Initialize database (creates tables if missing)
import db

app = FastAPI()

from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import RedirectResponse, JSONResponse

config = Config('.env')
oauth = OAuth(config)
import os
app.add_middleware(SessionMiddleware, secret_key=os.environ['SECRET_KEY'])

oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
    userinfo_endpoint='https://openidconnect.googleapis.com/v1/userinfo'
)

from fastapi import Request

@app.get("/api/user")
async def get_user(request: Request):
    user = request.session.get('user')
    if user:
        return JSONResponse(user)
    return JSONResponse({})

@app.get("/login")
async def login(request: Request):
    redirect_uri = request.url_for('auth')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback")
async def auth(request: Request):
    token = await oauth.google.authorize_access_token(request)
    print("Google token response:", token)  # Debug: see what's in the token
    user = None
    # Defensive: check for id_token in token
    if token and isinstance(token, dict) and "id_token" in token:
        try:
            user = await oauth.google.parse_id_token(request, token)
        except Exception as e:
            print("Failed to parse id_token:", e)
            user = None
    if not user:
        # Fallback: fetch userinfo from Google using httpx directly
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                'https://openidconnect.googleapis.com/v1/userinfo',
                headers={'Authorization': f'Bearer {token["access_token"]}'}
            )
            user = resp.json()
            print("Fetched userinfo from userinfo endpoint:", user)
    request.session['user'] = dict(user)
    return RedirectResponse(url="/")

@app.get("/logout")
def logout(request: Request):
    request.session.pop('user', None)
    return RedirectResponse(url="/")

# Serve static files (frontend build)
frontend_dist = os.path.join(os.path.dirname(__file__), 'static')
if not os.path.exists(frontend_dist):
    os.makedirs(frontend_dist)
app.mount("/static", StaticFiles(directory=frontend_dist, html=True), name="static")

# Serve images and segments as static files
images_dir = os.path.join(os.path.dirname(__file__), '..', 'images')
os.makedirs(images_dir, exist_ok=True)
app.mount("/images", StaticFiles(directory=images_dir), name="images")

segments_dir = os.path.join(os.path.dirname(__file__), '..', 'segments')
os.makedirs(segments_dir, exist_ok=True)
app.mount("/segments", StaticFiles(directory=segments_dir), name="segments")

# LLM Extraction Endpoint
class LLMRequest(BaseModel):
    text: str

@app.post("/api/llm")
def llm_extract(req: LLMRequest):
    ollama_url = "http://localhost:11434/api/generate"
    model = "llama3.1:8b"
    prompt = f"Extract keywords and entities from this text: {req.text}"
    print(f"[LLM] /api/llm called. Text: {req.text[:100]}... Model: {model}")
    try:
        resp = requests.post(ollama_url, json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2}
        }, timeout=30)
        print(f"[LLM] Ollama POST {ollama_url} status: {resp.status_code}")
        if not resp.ok:
            print(f"[LLM] Ollama error: {resp.status_code} {resp.text}")
            return JSONResponse(status_code=502, content={"error": "Ollama error", "status": resp.status_code})
        data = resp.json()
        print(f"[LLM] Ollama response: {str(data)[:200]}...")
        return {"response": data.get("response", "")}
    except Exception as e:
        print(f"[LLM] Exception: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
    print('[llm_extract] EXIT')

import re

class TranscriptRequest(BaseModel):
    url: str

def extract_video_id(url: str) -> str:
    print('[extract_video_id] ENTRY')
    # Handles various YouTube URL formats
    patterns = [
        r'(?:v=|youtu\.be/|embed/|shorts/)([\w-]{11})',
        r'youtube\.com/watch\?.*?v=([\w-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    # fallback: if the url itself is just the ID
    if re.match(r'^[\w-]{11}$', url):
        return url
    raise ValueError('Could not extract video ID from URL')
    print('[extract_video_id] EXIT')

from fastapi import Query
from fastapi.responses import JSONResponse

import base64
import json as pyjson

class GenerateSegmentsImagesRequest(BaseModel):
    videoId: str
    segments: list

@app.post("/api/generate-segments-images")
def generate_segments_images(req: GenerateSegmentsImagesRequest):
    print('[generate_segments_images] ENTRY')
    sd_url = "http://127.0.0.1:7860/sdapi/v1/txt2img"
    try:
        segments = req.segments
        if not isinstance(segments, list):
            raise ValueError("Segments must be a list")
        image_dir = os.path.join(os.path.dirname(__file__), '..', 'images')
        os.makedirs(image_dir, exist_ok=True)
        # Remove existing images for this video to avoid stale files
        try:
            for fname in os.listdir(image_dir):
                if fname.startswith(f"{req.videoId}_"):
                    try:
                        os.remove(os.path.join(image_dir, fname))
                        print(f"[GenerateSegmentsImages] Deleted old image {fname}")
                    except Exception as del_err:
                        print(f"[GenerateSegmentsImages] Failed to delete {fname}: {del_err}")
        except Exception as list_err:
            print(f"[GenerateSegmentsImages] Error listing images for cleanup: {list_err}")
        for seg in segments:
            if not ("start" in seg and "keyword" in seg):
                continue
            mmss = seg["start"].replace(":", "")
            img_filename = f"{req.videoId}_{mmss}.png"
            img_path = os.path.join(image_dir, img_filename)
            # Generate image with Stable Diffusion
            sd_payload = {"prompt": seg["keyword"], "steps": 20}
            sd_resp = requests.post(sd_url, json=sd_payload, timeout=120)
            if not sd_resp.ok:
                print(f"[StableDiffusion] Error for {seg['keyword']}: {sd_resp.status_code} {sd_resp.text}")
                seg["image"] = None
                continue
            sd_data = sd_resp.json()
            # Save image to disk
            if "images" in sd_data and sd_data["images"]:
                img_b64 = sd_data["images"][0]
                img_bytes = base64.b64decode(img_b64)
                with open(img_path, "wb") as f:
                    f.write(img_bytes)
                seg["image"] = img_filename
            else:
                seg["image"] = None
        
        print('IMAGE GENERATION COMPLETE')
        # ----------------- DB persistence -----------------
        from sqlmodel import Session, select
        from db import engine, Video, Segment
        with Session(engine) as session:
            # ensure Video row exists
            vid_row = session.get(Video, req.videoId)
            if vid_row is None:
                vid_row = Video(id=req.videoId)
                session.add(vid_row)
                session.commit()
            # delete old segments for this video
            from sqlmodel import delete as sqldelete
            session.exec(sqldelete(Segment).where(Segment.video_id == req.videoId))
            session.commit()
            to_add = []
            for seg in segments:
                # convert start to seconds
                if isinstance(seg["start"], str) and ":" in seg["start"]:
                    mm, ss = map(int, seg["start"].split(":"))
                    start_sec = mm*60 + ss
                else:
                    start_sec = int(seg["start"])
                to_add.append(Segment(
                    video_id=req.videoId,
                    start_sec=start_sec,
                    keyword=seg.get("keyword"),
                    text=seg.get("text"),
                    image_path=seg.get("image")
                ))
            session.add_all(to_add)
            session.commit()
        # ---------------------------------------------------
        return {"segments": segments}
    except Exception as e:
        print(f'[GenerateSegmentsImages] Exception: {e}')
        return JSONResponse(status_code=500, content={"error": str(e)})
    print('[generate_segments_images] EXIT')

class TopicKeywordsRequest(BaseModel):
    video_id: str = Field(alias="videoId")
    transcript: str

from fastapi import BackgroundTasks

@app.post("/api/topic-keywords")
def topic_keywords(req: TopicKeywordsRequest, bg: BackgroundTasks):
    segments_out = []  # will capture parsed segments later
    def _bg_task(video_id:str, segments:list):
        try:
            print('[BG] Generating images and persisting segments')
            import requests as _req
            _req.post("http://127.0.0.1:8000/api/generate-segments-images", json={"videoId": video_id, "segments": segments}, timeout=300)
        except Exception as bg_err:
            print(f'[BG] Error generating images: {bg_err}')

    print('[topic_keywords] ENTRY')
    ollama_url = "http://localhost:11434/api/generate"
    model = "llama3.1:8b"
    prompt = (
        "You are given a podcast transcript with timestamps.\n"
        "Segment the transcript into up to 10 meaningful topics.\n"
        "For each topic:\n"
        "- Provide the timestamp (in [MM:SS] format) where the topic begins\n"
        "- Generate ONE keyword (not multiple) that best represents that entire topic.\n"
        "Return a JSON list in this format:\n"
        "[\n  { \"start\": \"00:04\", \"keyword\": \"introduction\" },\n  ...\n]"
        "\nTranscript:\n" + req.transcript
    )
    print(f"[TopicKeywords] /api/topic-keywords called. Model: {model}")
    try:
        resp = requests.post(ollama_url, json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2}
        }, timeout=60)
        print(f"[TopicKeywords] Ollama POST {ollama_url} status: {resp.status_code}")
        if not resp.ok:
            print(f"[TopicKeywords] Ollama error: {resp.status_code} {resp.text}")
            return JSONResponse(status_code=502, content={"error": "Ollama error", "status": resp.status_code})
        data = resp.json()
        print(f"[TopicKeywords] Ollama response: {str(data)[:200]}...")
        # Try to parse the JSON from the LLM response
        import json
        try:
            raw_response = data.get("response", "[]")
            import re
            match = re.search(r'(\[.*?\])', raw_response, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                json_str = raw_response  # fallback to whole response
            segments = json.loads(json_str)
            # ---- DB persistence ----
            from sqlmodel import Session, delete as sqldelete
            from db import engine, Segment
            with Session(engine) as session:
                session.exec(sqldelete(Segment).where(Segment.video_id == req.video_id))
                to_add = []
                for seg in segments:
                    if isinstance(seg["start"], str):
                        mm, ss = map(int, seg["start"].split(":"))
                        start_sec = mm*60 + ss
                    else:
                        start_sec = int(seg["start"])
                    to_add.append(Segment(video_id=req.video_id, start_sec=start_sec, keyword=seg["keyword"]))
                session.add_all(to_add)
                session.commit()
            # schedule background task after DB insert
            bg.add_task(_bg_task, req.video_id, segments)
            # Validate segments: ensure each has start and keyword
            if not isinstance(segments, list):
                raise ValueError("Not a list")
            for seg in segments:
                if not ("start" in seg and "keyword" in seg):
                    raise ValueError("Missing fields in a segment")
            return {"segments": segments}
        except Exception as e:
            print(f"[TopicKeywords] JSON parse error: {e}")
            return JSONResponse(status_code=500, content={"error": "Failed to parse LLM output as JSON", "llm_response": data.get("response", "")})
    except Exception as e:
        print(f"[TopicKeywords] Exception: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
    print('[topic_keywords] EXIT')

def format_transcript(transcript):
    print('[format_transcript] ENTRY')
    return [
        {
            'text': seg.get('text', ''),
            'start': seg.get('start', 0),
            'duration': seg.get('duration', 0)
        } for seg in transcript
    ]
    print('[format_transcript] EXIT')

@app.post("/api/transcript/")
def fetch_transcript_post(req: TranscriptRequest):
    print('[fetch_transcript_post] ENTRY')
    print(f"[Transcript] /api/transcript/ POST called. URL: {req.url}")
    try:
        vid = extract_video_id(req.url)
        print(f"[Transcript] Extracted video_id: {vid}")
        transcript = YouTubeTranscriptApi.get_transcript(vid)
        print(f"[Transcript] Segments fetched: {len(transcript)}")
        formatted = format_transcript(transcript)
        # ---- DB persistence ----
        from sqlmodel import Session, delete as sqldelete
        from db import engine, TranscriptLine
        with Session(engine) as session:
            session.exec(sqldelete(TranscriptLine).where(TranscriptLine.video_id == vid))
            to_add = [TranscriptLine(video_id=vid, start_sec=int(line['start']), text=line['text']) for line in formatted]
            session.add_all(to_add)
            session.commit()
        return formatted
    except (TranscriptsDisabled, NoTranscriptFound):
        print(f"[Transcript] Transcript not available for video: {req.url}")
        return JSONResponse({'error': 'Transcript not available for this video.'}, status_code=404)
    except ValueError as ve:
        print(f"[Transcript] ValueError: {ve}")
        return JSONResponse({'error': str(ve)}, status_code=400)
    except Exception as e:
        print(f"[Transcript] Exception: {e}")
        return JSONResponse({'error': str(e)}, status_code=500)
    print('[fetch_transcript_post] EXIT')

@app.get("/api/transcript/")
def fetch_transcript_get(video_id: str = Query(None)):
    print('[fetch_transcript_get] ENTRY')
    print(f"[Transcript] /api/transcript/ GET called. video_id: {video_id}")
    try:
        if not video_id:
            print("[Transcript] Missing video_id in GET request")
            return JSONResponse({'error': 'Missing video_id'}, status_code=400)
        # ---- Try DB first ----
        from sqlmodel import Session, select, delete as sqldelete
        from db import engine, TranscriptLine
        with Session(engine) as session:
            rows = session.exec(select(TranscriptLine).where(TranscriptLine.video_id == video_id).order_by(TranscriptLine.start_sec)).all()
            if rows:
                print(f"[Transcript] Returning {len(rows)} lines from DB")
                return [
                    {"text": r.text, "start": r.start_sec, "duration": 0} for r in rows
                ]
        # ---- Fallback to YouTube ----
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        print(f"[Transcript] Segments fetched: {len(transcript)}")
        formatted = format_transcript(transcript)
        with Session(engine) as session:
            session.exec(sqldelete(TranscriptLine).where(TranscriptLine.video_id == video_id))
            to_add = [TranscriptLine(video_id=video_id, start_sec=int(line['start']), text=line['text']) for line in formatted]
            session.add_all(to_add)
            session.commit()
        return formatted
    except (TranscriptsDisabled, NoTranscriptFound):
        print(f"[Transcript] Transcript not available for video: {video_id}")
        return JSONResponse({'error': 'Transcript not available for this video.'}, status_code=404)
    except Exception as e:
        print(f"[Transcript] Exception: {e}")
        return JSONResponse({'error': str(e)}, status_code=500)

# ---------------------- DB read endpoint ----------------------
from sqlmodel import Session, select
from db import engine, Segment

@app.get("/api/segments/{video_id}")
def get_segments(video_id: str):
    """Return list of segments for a video from the DB in the legacy JSON shape."""
    with Session(engine) as session:
        rows = session.exec(
            select(Segment).where(Segment.video_id == video_id).order_by(Segment.start_sec)
        ).all()
        if not rows:
            return JSONResponse(status_code=404, content={"error": "No segments for this video"})
        def mmss(sec:int):
            return f"{sec//60:02d}:{sec%60:02d}"
        return [
            {
                "start": mmss(r.start_sec),
                "keyword": r.keyword,
                "text": r.text,
                "image": r.image_path,
            }
            for r in rows
        ]

# Fallback for SPA routes (serves index.html)
@app.get("/{full_path:path}")
def serve_spa(full_path: str, request: Request):
    # Only serve index.html for non-API, non-static routes
    if request.url.path.startswith("/api/") or request.url.path.startswith("/static/"):
        return JSONResponse({"error": "Not found"}, status_code=404)
    index_path = os.path.join(frontend_dist, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
