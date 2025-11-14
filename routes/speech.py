# routes/speech.py
from fastapi import APIRouter, UploadFile, File, HTTPException
import whisper, tempfile, os
import logging

router = APIRouter(prefix="/speech", tags=["speech"])

# Load model with error handling
try:
    _model = whisper.load_model(os.getenv("WHISPER_MODEL", "base"))
    print("✅ Whisper model loaded successfully")
except Exception as e:
    print(f"❌ Failed to load Whisper model: {e}")
    _model = None

@router.post("/upload-audio/")
async def upload_audio(file: UploadFile = File(...)):
    if _model is None:
        raise HTTPException(status_code=500, detail="Speech-to-text service not available")
    
    if not file.filename.lower().endswith(('.webm', '.wav', '.mp3', '.m4a')):
        raise HTTPException(status_code=400, detail="Unsupported audio format")
    
    print(f"🎤 Processing audio file: {file.filename}, size: {file.size}")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Empty audio file")
        
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        print("🔄 Transcribing audio...")
        result = _model.transcribe(tmp_path)
        text = result["text"].strip()
        print(f"📝 Transcription result: '{text}'")
        
        if not text:
            return {"transcription": "No speech detected in audio", "status": "empty"}
            
        return {"transcription": text, "status": "success"}
        
    except Exception as e:
        print(f"❌ Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
