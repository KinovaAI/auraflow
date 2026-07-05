"""AuraFlow — Voice Endpoints

Voice check-in (STT), voice commands, and raw audio transcription.
Supports browser-based speech recognition (text endpoint) and
OpenAI Whisper API (audio endpoint) for speech-to-text.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.api.v1.dependencies.rbac import require_permission
from app.services.ai.voice_service import VoiceService

router = APIRouter()
_voice = VoiceService()


class TextCheckinRequest(BaseModel):
    transcript: str


@router.post("/checkin/text")
async def text_checkin(
    body: TextCheckinRequest,
    _user=Depends(require_permission("voice.handle_sms_checkin")),
):
    """Text-based check-in: identify member from transcript and check them in.

    Use this with browser SpeechRecognition API — no OpenAI needed.
    """
    if not body.transcript.strip():
        raise HTTPException(status_code=400, detail="No text provided")

    try:
        result = await _voice.process_text_checkin(body.transcript.strip())
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/checkin")
async def voice_checkin(
    file: UploadFile = File(...),
    _user=Depends(require_permission("voice.handle_voice_checkin")),
):
    """Voice check-in: transcribe audio, identify member, check them in."""
    audio_data = await file.read()
    if not audio_data:
        raise HTTPException(status_code=400, detail="No audio data received")

    if len(audio_data) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="Audio file too large (max 10MB)")

    try:
        result = await _voice.process_voice_checkin(audio_data, filename=file.filename or "audio.webm")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/command")
async def voice_command(
    file: UploadFile = File(...),
    _user=Depends(require_permission("voice.handle_command")),
):
    """Voice navigation command: transcribe and parse a voice command."""
    audio_data = await file.read()
    if not audio_data:
        raise HTTPException(status_code=400, detail="No audio data received")

    if len(audio_data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Audio file too large (max 10MB)")

    try:
        result = await _voice.process_voice_command(audio_data, filename=file.filename or "audio.webm")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    _user=Depends(require_permission("voice.transcribe")),
):
    """Raw audio transcription — returns the text only."""
    audio_data = await file.read()
    if not audio_data:
        raise HTTPException(status_code=400, detail="No audio data received")

    if len(audio_data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Audio file too large (max 10MB)")

    try:
        text = await _voice.transcribe_audio(audio_data, filename=file.filename or "audio.webm")
        return {"transcript": text}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
