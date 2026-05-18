from dotenv import load_dotenv

load_dotenv()

import logging
import uuid

from fastapi import APIRouter, HTTPException

from mailwright.graphs.chat_graph import apply_rolling_summary, create_chat_graph_builder
from mailwright.graphs.checkpointer import get_checkpointer_context_manager
from mailwright.schemas.chat_schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/",
    response_model=ChatResponse,
    summary="Conversational email template assistant",
    description=(
        "Multi-turn chat that gathers requirements, generates an email template, "
        "handles revision requests, and approves the final version — all through "
        "natural language. Pass the returned `thread_id` on every subsequent message "
        "to continue the same conversation."
    ),
)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Single endpoint for the full template lifecycle via conversation:

    1. **Gathering** — assistant asks questions until it has enough info.
    2. **Generating** — template is created automatically once requirements are confirmed.
    3. **Review** — user can request as many changes as they like.
    4. **Approved** — user says "approve" and the template is finalised.

    Always include `thread_id` from the previous response to maintain context.
    Omit it (or send a new value) to start a fresh conversation.
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    lg_thread_id = f"chat_{thread_id}"

    try:
        async with get_checkpointer_context_manager() as checkpointer:
            chat_graph = create_chat_graph_builder(checkpointer).compile(
                checkpointer=checkpointer
            )
            config = {"configurable": {"thread_id": lg_thread_id}}

            # ---------------------------------------------------------------
            # Load existing message history so the LLM sees the full context.
            # ---------------------------------------------------------------
            snapshot = await chat_graph.aget_state(config)
            current_messages: list = []
            if snapshot and snapshot.values:
                current_messages = snapshot.values.get("messages", []) or []

            # Append the new user message.
            messages_with_user = current_messages + [
                {"role": "user", "content": request.message}
            ]

            # ---------------------------------------------------------------
            # Invoke the graph with the full updated message history.
            # The graph reads state.messages for LLM context; action nodes
            # update phase / template_id / etc. but never touch messages —
            # message persistence is handled here in the route.
            # ---------------------------------------------------------------
            result = await chat_graph.ainvoke(
                {"messages": messages_with_user}, config
            )

            final_reply: str = result.get(
                "assistant_reply", "I encountered an issue. Please try again."
            )

            # ---------------------------------------------------------------
            # Persist final messages with assistant reply.
            # Apply rolling summarisation so the checkpointer stays lean and
            # the LLM never receives a bloated context window in future turns.
            # ---------------------------------------------------------------
            final_messages = messages_with_user + [
                {"role": "assistant", "content": final_reply}
            ]
            compressed_messages = await apply_rolling_summary(final_messages)

            await chat_graph.aupdate_state(
                config,
                {"messages": compressed_messages, "pending_action": None},
            )

            template_id: str | None = result.get("template_id")
            version_id: str | None = result.get("current_version_id")
            phase: str = result.get("phase", "gathering")

            html_preview_url: str | None = (
                f"/api/v1/templates/{template_id}/versions/{version_id}/html"
                if template_id and version_id
                else None
            )

            return ChatResponse(
                reply=final_reply,
                thread_id=thread_id,
                phase=phase,
                template_id=template_id,
                current_version_id=version_id,
                html_preview_url=html_preview_url,
            )

    except Exception as exc:
        logger.error(f"Chat endpoint error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
