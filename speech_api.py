# speech_api.py
# ==========================================================
# FastAPI backend for audio transcription using OpenAI Whisper.
# Accepts uploaded audio (from AudioRecorder frontend) and
# returns the transcribed text in JSON format.
# ==========================================================

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import whisper, tempfile, os

# ---------- App Initialization ----------
app = FastAPI(title="Speech Transcription API")

# Enable CORS so the React frontend can call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Use ["http://localhost:5173"] for stricter security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load Whisper model once on startup (base model = good balance of speed & accuracy)
model = whisper.load_model("base")

# ==========================================================
# API Endpoint: /speech/upload-audio/
# ==========================================================
@app.post("/speech/upload-audio/")
async def upload_audio(file: UploadFile = File(...)):
    """
    Receive a recorded .webm or .wav file from the frontend,
    save it temporarily, run Whisper transcription,
    and return the transcribed text as JSON.
    """
    # Save the uploaded file temporarily for processing
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    # Run Whisper transcription
    try:
        result = model.transcribe(tmp_path)
        text = result["text"].strip()
    finally:
        os.remove(tmp_path)  # Clean up temp file

    return {"transcription": text}

