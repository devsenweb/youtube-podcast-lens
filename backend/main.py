from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import requests
import os

app = FastAPI()

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

from pydantic import BaseModel
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
        # Save segment metadata
        segments_dir = os.path.join(os.path.dirname(__file__), '..', 'segments')
        os.makedirs(segments_dir, exist_ok=True)
        segments_json_path = os.path.join(segments_dir, f"{req.videoId}.json")
        with open(segments_json_path, "w", encoding="utf-8") as f:
            pyjson.dump(segments, f, ensure_ascii=False, indent=2)
        print(f"[GenerateSegmentsImages] Saved segments to {segments_json_path}")
        return {"segments": segments}
    except Exception as e:
        print(f"[GenerateSegmentsImages] Exception: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
    print('[generate_segments_images] EXIT')

class TopicKeywordsRequest(BaseModel):
    transcript: str

@app.post("/api/topic-keywords")
def topic_keywords(req: TopicKeywordsRequest):
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
        return format_transcript(transcript)
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
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        print(f"[Transcript] Segments fetched: {len(transcript)}")
        return format_transcript(transcript)
    except (TranscriptsDisabled, NoTranscriptFound):
        print(f"[Transcript] Transcript not available for video: {video_id}")
        return JSONResponse({'error': 'Transcript not available for this video.'}, status_code=404)
    except Exception as e:
        print(f"[Transcript] Exception: {e}")
        return JSONResponse({'error': str(e)}, status_code=500)

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
