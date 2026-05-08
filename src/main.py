from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from config.logging_config import configure_logging
from common.middleware.performance_middleware import PerformanceMonitoringMiddleware
from common.routes.startup import startup_event
from admin.routes import admin_router
from student.routes import student_router
from teacher.routes import vector_router
from teacher.routes.topics import router as topics_router
from common.routes import auth_router, performance_router, activity_router, core_router
from teacher.services.vector_creator import create_vectors_service
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from common.services.tts_service import generate_audio_stream
from config.settings import settings

configure_logging()

app = FastAPI(
    title=settings.app_name,
    description="AI-powered adaptive learning backend. RAG-powered student tutoring with vector search, multi-language support, and performance analytics.",
    version="0.1.0",
    contact={
        "name": "Student Learning API Team",
    },
    license_info={
        "name": "MIT",
    },
)


class TTSRequest(BaseModel):
    text: str
    voice: str = settings.tts_default_voice
    rate: str = "+0%"


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


app.state.create_vectors_service = create_vectors_service

if settings.environment == "development":
    # Allow any origin in dev (ngrok URLs change, mobile testing, etc.)
    # Credentials are sent via Authorization header, not cookies, so wildcard is safe
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    origins = settings.cors_origins_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Add performance monitoring middleware
# app.add_middleware(PerformanceMonitoringMiddleware)


@app.on_event("startup")
async def on_startup():
    await startup_event(app)


api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(
    auth_router,
    prefix="/auth",
    tags=["Authentication"]
)

api_v1_router.include_router(
    student_router,
    prefix="/student",
    tags=["Student"]
)

api_v1_router.include_router(
    admin_router,
    prefix="/admin",
    tags=["Admin"]
)

api_v1_router.include_router(
    vector_router,
    prefix="/vectors",
    tags=["Vectors"]
)

api_v1_router.include_router(
    performance_router,
    prefix="/performance",
    tags=["Performance"]
)

api_v1_router.include_router(
    activity_router,
    prefix="/activity",
    tags=["Activity Tracking"]
)

api_v1_router.include_router(
    core_router,
    prefix="/core",
    tags=["Core"]
)

api_v1_router.include_router(
    topics_router,
    prefix="/topics",
    tags=["Topics"]
)

app.include_router(api_v1_router)
