"""
Chat Graph — powers the POST /api/v1/chat conversational endpoint.

Lifecycle
---------
gathering → (requirements complete) → generate → review → (approve) → approved
                                                          → (feedback) → review
"""

import logging
import uuid
from typing import Any, Dict, List, Literal, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from mailwright.config import settings
from mailwright.db.models import AsyncSessionLocal
from mailwright.db.template_store import approve_template_version, get_template_version

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rolling summarization — Strategy 2 from context_engineering.md
# ---------------------------------------------------------------------------
#
# When the conversation grows beyond _SUMMARY_THRESHOLD messages, every turn
# we compress anything older than the last _KEEP_RECENT messages into a single
# compact summary block.  The summary replaces the old messages in the
# persisted state so the checkpointer stays lean and the LLM never sees a
# bloated context window.
#
# Trigger  : total messages > _SUMMARY_THRESHOLD
# Preserved: last _KEEP_RECENT messages verbatim
# Compressed: all older messages → one summary "assistant" message

_SUMMARY_THRESHOLD: int = 10   # start compressing after 10 messages (~5 turns)
_KEEP_RECENT: int = 6          # always keep the 6 most-recent messages verbatim

_ROLLING_SUMMARY_SYSTEM = (
    "You are summarizing a conversation between a user and mailwright, "
    "an email template creation assistant.\n"
    "Produce a concise summary (max 180 words) that preserves EVERY confirmed decision:\n"
    "  • email subject, body copy, CTA text, CTA URL\n"
    "  • image descriptions (if any)\n"
    "  • template ID and version IDs (if generated)\n"
    "  • any approved or pending changes\n"
    "Use bullet points. Do not include greetings or filler."
)


async def apply_rolling_summary(
    messages: List[Dict[str, str]],
    threshold: int = _SUMMARY_THRESHOLD,
    keep_recent: int = _KEEP_RECENT,
) -> List[Dict[str, str]]:
    """
    Rolling Summarization (Strategy 2).

    Returns the same list unchanged if it is still below *threshold*.
    Otherwise, compresses everything older than *keep_recent* into a single
    summary message prepended to the retained tail.

    On LLM failure the original list is returned unchanged so no history
    is ever silently lost.
    """
    if len(messages) <= threshold:
        return messages

    old_messages = messages[:-keep_recent]
    recent_messages = messages[-keep_recent:]

    # Format the old turns for the summarizer.
    formatted_history = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in old_messages
    )

    try:
        llm = _get_llm()
        response = await llm.ainvoke(
            [
                SystemMessage(content=_ROLLING_SUMMARY_SYSTEM),
                HumanMessage(content=formatted_history),
            ]
        )
        summary_text: str = response.content
        logger.info(
            f"apply_rolling_summary: compressed {len(old_messages)} messages "
            f"→ ~{len(summary_text)} chars"
        )
    except Exception as exc:
        logger.warning(
            f"apply_rolling_summary: LLM call failed ({exc}), keeping full history."
        )
        return messages  # graceful fallback — never lose history

    # Inject summary as a special assistant message so the LLM sees it in context.
    summary_message: Dict[str, str] = {
        "role": "assistant",
        "content": f"[CONVERSATION SUMMARY — earlier turns]\n{summary_text}",
    }

    return [summary_message] + recent_messages


# ---------------------------------------------------------------------------
# Chat state
# ---------------------------------------------------------------------------

class ChatState(BaseModel):
    """Persisted state for a single chat session (thread_id = chat_{user_id})."""

    # Full conversation history stored as simple dicts for easy serialisation.
    messages: List[Dict[str, str]] = []

    # Current phase of the conversation.
    phase: str = "gathering"  # gathering | review | approved | error

    # Brief fields collected during the gathering phase.
    brief_subject: Optional[str] = None
    brief_body_copy: Optional[str] = None
    brief_cta_text: Optional[str] = None
    brief_cta_url: Optional[str] = None
    brief_image_suggestions: Optional[List[str]] = None

    # Template lifecycle — set once generation succeeds.
    template_id: Optional[str] = None
    current_version_id: Optional[str] = None

    # Intra-turn signals set by chat_conversation_node, consumed by routing.
    pending_action: Optional[str] = None  # start_generation | submit_feedback | approve
    pending_feedback_text: Optional[str] = None

    # The reply to send back to the caller this turn.
    assistant_reply: Optional[str] = None

    error_message: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True


# ---------------------------------------------------------------------------
# Structured LLM output
# ---------------------------------------------------------------------------

class ChatLLMDecision(BaseModel):
    """
    Structured output returned by the conversational LLM each turn.
    All fields except reply_to_user are optional depending on the action.
    """

    reply_to_user: str

    # null | start_generation | submit_feedback | approve
    action: Optional[Literal["start_generation", "submit_feedback", "approve"]] = None

    # Populated when action == "start_generation"
    subject: Optional[str] = None
    body_copy: Optional[str] = None
    cta_text: Optional[str] = None
    cta_url: Optional[str] = None
    image_suggestions: Optional[List[str]] = None

    # Populated when action == "submit_feedback"
    feedback_text: Optional[str] = None


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_GATHERING_SYSTEM_PROMPT = """You are mailwright, a dedicated email marketing template creation assistant.

⚠️  SCOPE RULE — STRICTLY ENFORCED:
You only help with creating email marketing templates. If the user asks ANYTHING unrelated
(general knowledge, coding, jokes, current events, other topics), politely decline and
redirect them back to the template task. Example redirect:
"I'm mailwright, your email template assistant — I can only help with creating email templates!
Let's get back to it. [continue with next relevant question]"

Your goal is to gather information to build a great email template through natural conversation.

You MUST collect (in order of priority):
  1. subject     — the email subject line
  2. body_copy   — the main message / content of the email
  3. cta_text    — call-to-action button label (e.g. "Shop Now", "Get Started")
  4. cta_url     — URL the button links to (a placeholder like https://example.com is fine)
  5. images      — ALWAYS ask "Would you also like to add images to the template?" once you
                   have the 4 fields above. If yes, ask them to briefly describe each image
                   (e.g. "a hero banner of a woman shopping").  If no, that is fine.

Rules:
1. Be warm and conversational — ask 1-2 questions at a time, never dump a long form.
2. Step 5 (image question) is MANDATORY — you must ask it before confirming generation,
   even if the user gave you all 4 required fields in one message.
3. After the image question is answered (yes with descriptions, or no), summarise what
   you've gathered and ask if the user is ready to generate.
4. When the user confirms they want to go ahead, set action="start_generation" and
   populate ALL collected fields (image_suggestions can be an empty list if they said no).
5. Never ask about images more than once.

Currently collected:
{collected_info}"""


_REVIEW_SYSTEM_PROMPT = """You are mailwright, a dedicated email template assistant. A template has just been generated.

⚠️  SCOPE RULE — STRICTLY ENFORCED:
You only help with reviewing and refining email marketing templates. If the user asks
ANYTHING unrelated (general knowledge, coding, jokes, other topics), politely decline
and redirect them back to reviewing their template. Example:
"I'm mailwright, your email template assistant — I can only help with your template!
Here's the preview link again: /api/v1/templates/{template_id}/versions/{version_id}/html"

Template details:
  • Preview URL : /api/v1/templates/{template_id}/versions/{version_id}/html
  • MJML source : /api/v1/templates/{template_id}/versions/{version_id}/mjml

Help the user review and refine the template. Handle exactly three cases:

1. CHANGE REQUEST — user wants to modify something (text, colours, layout, images, CTA, etc.).
   → Set action="submit_feedback" and write a clear, specific feedback_text describing the change.

2. APPROVAL — user is satisfied and ready to finalise
   (e.g. "looks good", "approve it", "perfect", "I'm happy with this").
   → Set action="approve"

3. QUESTION / GENERAL — anything else that is still about the template or email marketing.
   → Reply conversationally, action stays null.

4. OUT OF SCOPE — anything unrelated to the template or email marketing.
   → Politely decline and redirect, action stays null.

Remind users they can request as many changes as they like before approving."""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_llm() -> ChatOpenAI:
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required for the chat service.")
    return ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model=settings.MJML_GENERATION_OPENAI_MODEL,
        temperature=0.7,
    )


# ---------------------------------------------------------------------------
# Node 1 — conversation (gathering + review)
# ---------------------------------------------------------------------------

async def chat_conversation_node(state: ChatState, config: dict) -> Dict[str, Any]:
    """
    Main LLM node.  Reads message history, decides what to do next, and returns
    state updates (never touches the messages list — that is managed by the route).
    """
    logger.info(f"--- chat_conversation_node | phase={state.phase} ---")
    updates: Dict[str, Any] = {}

    llm = _get_llm().with_structured_output(ChatLLMDecision)

    # Build the appropriate system prompt.
    if state.phase == "gathering":
        parts = []
        if state.brief_subject:
            parts.append(f"  subject      : {state.brief_subject}")
        if state.brief_body_copy:
            snippet = state.brief_body_copy[:120] + ("…" if len(state.brief_body_copy) > 120 else "")
            parts.append(f"  body_copy    : {snippet}")
        if state.brief_cta_text:
            parts.append(f"  cta_text     : {state.brief_cta_text}")
        if state.brief_cta_url:
            parts.append(f"  cta_url      : {state.brief_cta_url}")
        if state.brief_image_suggestions:
            parts.append(f"  images       : {state.brief_image_suggestions}")
        collected_info = "\n".join(parts) if parts else "  (nothing yet)"
        system_content = _GATHERING_SYSTEM_PROMPT.format(collected_info=collected_info)
    else:
        system_content = _REVIEW_SYSTEM_PROMPT.format(
            template_id=state.template_id or "N/A",
            version_id=state.current_version_id or "N/A",
        )

    # Build LangChain message list from stored history.
    lc_messages = [SystemMessage(content=system_content)]
    for msg in state.messages:
        if msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        else:
            lc_messages.append(AIMessage(content=msg["content"]))

    try:
        decision: ChatLLMDecision = await llm.ainvoke(lc_messages)
    except Exception as exc:
        logger.error(f"chat_conversation_node LLM error: {exc}", exc_info=True)
        updates["assistant_reply"] = "Sorry, I ran into a problem. Please try again."
        updates["pending_action"] = None
        return updates

    updates["assistant_reply"] = decision.reply_to_user
    updates["pending_action"] = decision.action

    # Carry forward any newly extracted brief fields.
    if decision.action == "start_generation":
        if decision.subject:
            updates["brief_subject"] = decision.subject
        if decision.body_copy:
            updates["brief_body_copy"] = decision.body_copy
        if decision.cta_text:
            updates["brief_cta_text"] = decision.cta_text
        if decision.cta_url:
            updates["brief_cta_url"] = decision.cta_url
        if decision.image_suggestions:
            updates["brief_image_suggestions"] = decision.image_suggestions

    if decision.action == "submit_feedback":
        updates["pending_feedback_text"] = decision.feedback_text

    logger.info(f"chat_conversation_node → action={decision.action}")
    return updates


# ---------------------------------------------------------------------------
# Node 2 — template generation (closure over checkpointer)
# ---------------------------------------------------------------------------

def _make_generate_template_node(checkpointer):
    async def generate_template_node(state: ChatState, config: dict) -> Dict[str, Any]:
        """
        Runs the existing template-generation LangGraph graph inline.
        Sets clarification_rounds_count=1 so the BriefAnalyzer is lenient —
        requirements were already gathered through conversation.
        """
        logger.info("--- generate_template_node ---")
        updates: Dict[str, Any] = {}
        template_id = str(uuid.uuid4())

        try:
            # Import here to avoid circular imports at module load time.
            from mailwright.graphs.state import GraphState
            from mailwright.graphs.template_generation_graph import create_graph_builder

            initial_state = GraphState(
                user_brief_data={
                    "subject": state.brief_subject or "",
                    "body_copy": state.brief_body_copy or "",
                    "cta_text": state.brief_cta_text or "",
                    "cta_url": state.brief_cta_url or "https://example.com",
                    "image_suggestions": state.brief_image_suggestions or [],
                },
                rag_flow=False,
                # Start in round 1 so BriefAnalyzer is lenient about completeness.
                clarification_rounds_count=1,
                # Pass image prompts so the image generation node picks them up.
                # If the user said "no images", this is None and the node skips silently.
                image_prompts=state.brief_image_suggestions if state.brief_image_suggestions else None,
            )

            template_graph = create_graph_builder().compile(checkpointer=checkpointer)
            template_config = {"configurable": {"thread_id": template_id}}

            result = await template_graph.ainvoke(
                initial_state.model_dump(), template_config
            )

            status = result.get("last_operation_status", "")

            if status == "SUCCESS_STORED_V0":
                updates["template_id"] = template_id
                updates["current_version_id"] = "v0"
                updates["phase"] = "review"
                updates["pending_action"] = None
                updates["assistant_reply"] = (
                    f"Your email template is ready! 🎉\n\n"
                    f"**Preview:** `/api/v1/templates/{template_id}/versions/v0/html`\n\n"
                    f"Open that URL to see your template. Tell me if you'd like any changes "
                    f"(colours, text, layout, images) or say **'approve'** when you're happy."
                )
            else:
                err = result.get("error_message", "Unknown error during generation.")
                updates["error_message"] = err
                updates["pending_action"] = None
                updates["assistant_reply"] = (
                    f"I ran into an issue generating your template: {err}\n\n"
                    f"Would you like to adjust the brief and try again?"
                )

        except Exception as exc:
            logger.error(f"generate_template_node error: {exc}", exc_info=True)
            updates["error_message"] = str(exc)
            updates["pending_action"] = None
            updates["assistant_reply"] = (
                f"Something went wrong during template generation: {exc}\n\n"
                f"Would you like to try again?"
            )

        return updates

    return generate_template_node


# ---------------------------------------------------------------------------
# Node 3 — feedback / revision (closure over checkpointer)
# ---------------------------------------------------------------------------

def _make_submit_feedback_node(checkpointer):
    async def submit_feedback_node(state: ChatState, config: dict) -> Dict[str, Any]:
        """
        Injects the user's natural-language change request into the existing
        template-generation graph and re-invokes it so the FeedbackEngine node runs.
        """
        logger.info(
            f"--- submit_feedback_node | template={state.template_id} version={state.current_version_id} ---"
        )
        updates: Dict[str, Any] = {}

        if not state.template_id or not state.current_version_id:
            updates["assistant_reply"] = (
                "I couldn't find the template to revise. Something went wrong."
            )
            updates["pending_action"] = None
            return updates

        feedback_text = state.pending_feedback_text or "Please improve the template."

        try:
            from mailwright.graphs.template_generation_graph import create_graph_builder

            # Load current MJML from the database.
            async with AsyncSessionLocal() as db:
                version = await get_template_version(
                    db, state.template_id, state.current_version_id
                )

            if not version or not version.mjml_source:
                updates["assistant_reply"] = (
                    "I couldn't load the current template version for revision. "
                    "Please try again."
                )
                updates["pending_action"] = None
                return updates

            # Re-invoke the template graph using the same pattern as
            # template_routes.submit_template_feedback: pass the feedback
            # as direct input to ainvoke (not via aupdate_state) so LangGraph
            # merges it with the existing state and re-routes from START.
            template_graph = create_graph_builder().compile(checkpointer=checkpointer)
            template_config = {"configurable": {"thread_id": state.template_id}}

            result = await template_graph.ainvoke(
                {
                    "user_feedback_content": feedback_text,
                    "version_id_for_feedback": state.current_version_id,
                    "current_mjml": version.mjml_source,
                    "last_operation_status": "FEEDBACK_RECEIVED",
                    "error_message": None,
                    "clarification_questions": None,
                },
                template_config,
            )

            status = result.get("last_operation_status", "")
            new_version_id = result.get("current_version_id_stored")

            if status == "SUCCESS_STORED_REVISED_VERSION" and new_version_id:
                updates["current_version_id"] = new_version_id
                updates["pending_feedback_text"] = None
                updates["pending_action"] = None
                updates["assistant_reply"] = (
                    f"Done! I've applied your changes. Here's the revised template:\n\n"
                    f"**Preview:** `/api/v1/templates/{state.template_id}/versions/{new_version_id}/html`\n\n"
                    f"Let me know if you'd like further changes or say **'approve'** when satisfied."
                )
            else:
                err = result.get("error_message", "Revision failed.")
                updates["pending_action"] = None
                updates["assistant_reply"] = (
                    f"I had trouble applying your changes: {err}\n\n"
                    f"Could you rephrase your request?"
                )

        except Exception as exc:
            logger.error(f"submit_feedback_node error: {exc}", exc_info=True)
            updates["pending_action"] = None
            updates["assistant_reply"] = (
                f"Something went wrong while applying your changes: {exc}"
            )

        return updates

    return submit_feedback_node


# ---------------------------------------------------------------------------
# Node 4 — approval
# ---------------------------------------------------------------------------

async def approve_template_node(state: ChatState, config: dict) -> Dict[str, Any]:
    """Marks the current version as approved in the database."""
    logger.info(
        f"--- approve_template_node | template={state.template_id} version={state.current_version_id} ---"
    )
    updates: Dict[str, Any] = {}

    if not state.template_id or not state.current_version_id:
        updates["assistant_reply"] = (
            "I couldn't find the template to approve. Something went wrong."
        )
        updates["pending_action"] = None
        return updates

    try:
        async with AsyncSessionLocal() as db:
            await approve_template_version(
                db, state.template_id, state.current_version_id
            )

        updates["phase"] = "approved"
        updates["pending_action"] = None
        updates["assistant_reply"] = (
            f"Your email template has been approved! ✅\n\n"
            f"**Template ID :** `{state.template_id}`\n"
            f"**Approved version :** `{state.current_version_id}`\n"
            f"**Final HTML :** "
            f"`/api/v1/templates/{state.template_id}/versions/{state.current_version_id}/html`\n\n"
            f"Your template is ready to use. Is there anything else I can help you with?"
        )
    except Exception as exc:
        logger.error(f"approve_template_node error: {exc}", exc_info=True)
        updates["pending_action"] = None
        updates["assistant_reply"] = (
            f"I ran into an issue approving your template: {exc}"
        )

    return updates


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

_NODE_GENERATE = "LG_Chat_Generate"
_NODE_FEEDBACK = "LG_Chat_Feedback"
_NODE_APPROVE = "LG_Chat_Approve"
_NODE_CONVERSATION = "LG_Chat_Conversation"


def _route_after_conversation(state: ChatState) -> str:
    action = state.pending_action
    if action == "start_generation":
        return _NODE_GENERATE
    if action == "submit_feedback" and state.template_id:
        return _NODE_FEEDBACK
    if action == "approve" and state.template_id:
        return _NODE_APPROVE
    return END


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def create_chat_graph_builder(checkpointer) -> StateGraph:
    """
    Assembles the chat StateGraph.  Requires a checkpointer so the generation
    and feedback nodes can compile the template sub-graph with the same
    persistence backend.
    """
    builder = StateGraph(ChatState)

    builder.add_node(_NODE_CONVERSATION, chat_conversation_node)
    builder.add_node(_NODE_GENERATE, _make_generate_template_node(checkpointer))
    builder.add_node(_NODE_FEEDBACK, _make_submit_feedback_node(checkpointer))
    builder.add_node(_NODE_APPROVE, approve_template_node)

    # Every turn starts at the conversation node.
    builder.add_edge(START, _NODE_CONVERSATION)

    builder.add_conditional_edges(
        _NODE_CONVERSATION,
        _route_after_conversation,
        {
            _NODE_GENERATE: _NODE_GENERATE,
            _NODE_FEEDBACK: _NODE_FEEDBACK,
            _NODE_APPROVE: _NODE_APPROVE,
            END: END,
        },
    )

    # All action nodes terminate the turn.
    builder.add_edge(_NODE_GENERATE, END)
    builder.add_edge(_NODE_FEEDBACK, END)
    builder.add_edge(_NODE_APPROVE, END)

    return builder
