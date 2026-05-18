from dotenv import load_dotenv

load_dotenv()

from typing import Literal, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    phase: str  # gathering | review | approved | error
    template_id: Optional[str] = None
    current_version_id: Optional[str] = None
    html_preview_url: Optional[str] = None
