"""Minimal OpenAI-compatible Whisper transcription server."""

import os
import tempfile

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel

MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")

app = FastAPI(title="Whisper Transcription Server")
model: WhisperModel | None = None


def get_model() -> WhisperModel:
    global model
    if model is None:
        model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    return model


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form("small"),
    language: str | None = Form(None),
    prompt: str | None = Form(None),
):
    audio_bytes = await file.read()

    suffix = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        whisper = get_model()
        segments, info = whisper.transcribe(
            tmp_path,
            language=language,
            initial_prompt=prompt,
            beam_size=5,
        )
        text = " ".join(segment.text.strip() for segment in segments)
    finally:
        os.unlink(tmp_path)

    return JSONResponse(
        content={
            "text": text,
            "language": info.language,
            "duration": info.duration,
        }
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("WHISPER_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
