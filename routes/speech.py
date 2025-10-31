# routes/speech.py
from fastapi import APIRouter, UploadFile, File
import whisper, tempfile, os

router = APIRouter(prefix="/speech", tags=["speech"])
_model = whisper.load_model(os.getenv("WHISPER_MODEL", "base"))

@router.post("/upload-audio/")
async def upload_audio(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result = _model.transcribe(tmp_path)
        text = result["text"].strip()
    finally:
        os.remove(tmp_path)
    return {"transcription": text}
