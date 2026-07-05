"""AuraFlow — AI Chatbot Endpoints

SSE-streaming chat assistant powered by Claude. Supports multi-turn
conversations with tool use. All endpoints require authentication.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.v1.dependencies.auth import get_current_user
from app.services.ai.chatbot_service import ChatbotService

router = APIRouter()
_chatbot = ChatbotService()


# ── Request/Response Schemas ──────────────────────────────────────────────────

class ChatMessageRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class CreateConversationRequest(BaseModel):
    title: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/message")
async def send_message(
    body: ChatMessageRequest,
    user: dict = Depends(get_current_user),
):
    """
    Send a message to the AI assistant and receive a streaming SSE response.

    The response is a Server-Sent Events stream with these event types:
    - conversation_id: the conversation this message belongs to
    - content_delta: incremental text chunks from the assistant
    - tool_use: a tool was called (includes name and result)
    - action: a UI action to perform (e.g., navigate to a page)
    - error: an error occurred
    - done: stream is complete
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_role = user.get("org_role", "member")
    if user.get("is_platform_admin"):
        user_role = "platform_admin"

    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if len(body.message) > 5000:
        raise HTTPException(status_code=400, detail="Message too long (max 5000 characters)")

    return StreamingResponse(
        _chatbot.stream_message(
            user_id=user_id,
            conversation_id=body.conversation_id,
            message=body.message.strip(),
            user_role=user_role,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations")
async def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """List the current user's recent chatbot conversations."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    conversations = await _chatbot.list_conversations(user_id, limit=limit)
    return {"data": conversations}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: dict = Depends(get_current_user),
):
    """Get a conversation with all its messages."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    conversation = await _chatbot.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Ensure the conversation belongs to this user
    if conversation["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"data": conversation}


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    user: dict = Depends(get_current_user),
):
    """Delete a conversation and all its messages."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    deleted = await _chatbot.delete_conversation(conversation_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.post("/conversations", status_code=201)
async def create_conversation(
    body: CreateConversationRequest,
    user: dict = Depends(get_current_user),
):
    """Create a new empty conversation."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    conv_id = await _chatbot.create_conversation(user_id, title=body.title)
    return {"data": {"id": conv_id, "title": body.title}}
