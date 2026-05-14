# from fastapi import FastAPI
# from fastapi.responses import StreamingResponse
# from pydantic import BaseModel

# # 👇 import your function here
# from tts_service import generate_audio_stream

# app = FastAPI()


# class TTSRequest(BaseModel):
#     text: str
#     voice: str = "en-US-AriaNeural"


# @app.post("/tts-stream")
# async def tts_stream(request: TTSRequest):
#     audio_stream = generate_audio_stream(
#         text=request.text,
#         voice=request.voice
#     )

#     return StreamingResponse(
#         audio_stream,
#         media_type="audio/mpeg",
#         headers={
#             "Content-Disposition": "inline; filename=speech.mp3"
#         }
#     )


from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from tts_service import generate_audio_stream

app = FastAPI()

class TTSRequest(BaseModel):
    text: str
    voice: str = "en-US-AriaNeural"
    rate: str = "+0%"   # 👈 add speed control


@app.post("/tts-stream")
async def tts_stream(request: TTSRequest):
    audio_stream = generate_audio_stream(
        text=request.text,
        voice=request.voice,
        rate=request.rate
    )

    return StreamingResponse(
        audio_stream,
        media_type="audio/mpeg"
    )