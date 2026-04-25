"""
Notes endpoints.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, field_validator

from src.auth.auth_service import AuthIdentity, get_current_identity
from src.utils import get_logger
from src.db.cosmos_client import get_cosmos_client

logger = get_logger(__name__)
router = APIRouter(prefix="/notes", tags=["notes"])


class Note(BaseModel):
    """Note model."""
    id: Optional[str] = None
    user_id: Optional[str] = None
    content: str
    created_at: Optional[str] = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Note content cannot be empty")
        return value.strip()


@router.get("")
async def get_notes(
    current_user: AuthIdentity = Depends(get_current_identity),
    limit: int = Query(default=10, ge=1, le=100),
):
    """Get user's notes."""
    try:
        client = get_cosmos_client()
        notes = await run_in_threadpool(client.get_user_notes, current_user.user_id, limit)
        return {"notes": notes}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting notes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def add_note(
    note: Note,
    current_user: AuthIdentity = Depends(get_current_identity),
):
    """Add a new note."""
    try:
        client = get_cosmos_client()
        note_data = note.model_dump(exclude_unset=True, exclude_none=True)
        note_data["user_id"] = current_user.user_id
        added_note = await run_in_threadpool(client.add_note, note_data)
        return added_note
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding note: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{note_id}")
async def delete_note(
    note_id: str,
    current_user: AuthIdentity = Depends(get_current_identity),
):
    """Delete a note."""
    try:
        client = get_cosmos_client()
        success = await run_in_threadpool(client.delete_note, note_id, current_user.user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Note not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting note: {e}")
        raise HTTPException(status_code=500, detail=str(e))
