"""
Vector search routes
Handles vector search operations and query generation
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()

class SearchRequest(BaseModel):
    query: str
    class_: str
    subject: str

@router.post("/search")
def search(payload: SearchRequest, request: Request):
    from teacher.repositories.search_chunk import search_and_generate
    
    return search_and_generate(
        query=payload.query,
        class_=payload.class_,
        subject=payload.subject,
        embedding_model=request.app.state.embedding_model,
    )
