"""
mailwright — Email Template Assistant  |  Gradio UI  (Gradio 6.x compatible)
────────────────────────────────────────────────────────────────────────
Run:  python ui/app.py
Then open http://localhost:7860 in your browser.

The FastAPI backend must be running at API_BASE (default http://localhost:8000).
"""

import requests
import gradio as gr

DEFAULT_API_BASE = "http://localhost:8000"


# ── Helpers ────────────────────────────────────────────────────────────────

def _phase_badge(phase: str) -> str:
    meta = {
        "gathering": ("#f59e0b", "🔍  Gathering requirements"),
        "review":    ("#3b82f6", "👁️   Review & revise"),
        "approved":  ("#22c55e", "✅  Approved"),
        "error":     ("#ef4444", "❌  Error"),
    }
    color, label = meta.get(phase, ("#6b7280", f"• {phase}"))
    return (
        f'<div style="text-align:center;padding:6px 0">'
        f'<span style="background:{color};color:#fff;padding:6px 18px;'
        f'border-radius:999px;font-weight:700;font-size:.83rem;letter-spacing:.4px">'
        f"{label}</span></div>"
    )


def _call_api(api_base: str, message: str, thread_id) -> dict:
    url = f"{api_base.rstrip('/')}/api/v1/chat/"
    payload: dict = {"message": message}
    if thread_id:
        payload["thread_id"] = thread_id
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


# ── Core handler ───────────────────────────────────────────────────────────

def send_message(
    user_msg: str,
    history: list,
    thread_id,
    phase: str,
    template_id,
    version_id,
    api_base: str,
):
    if not user_msg.strip():
        return (
            history,
            _phase_badge(phase),
            thread_id, thread_id or "—",
            phase,
            template_id, template_id or "—",
            version_id, version_id or "—",
            "",
        )

    # Append user message immediately (Gradio 6 messages format)
    history = history + [{"role": "user", "content": user_msg}]

    try:
        data = _call_api(api_base, user_msg, thread_id)

    except requests.exceptions.Timeout:
        history.append({
            "role": "assistant",
            "content": (
                "⚠️ **Request timed out** — template generation can take 60–90 s. "
                "Send any message to check if it completed, or try again."
            ),
        })
        return (
            history,
            _phase_badge(phase),
            thread_id, thread_id or "—",
            phase,
            template_id, template_id or "—",
            version_id, version_id or "—",
            "",
        )

    except requests.exceptions.ConnectionError:
        history.append({
            "role": "assistant",
            "content": (
                f"⚠️ **Could not connect** to the API at `{api_base}`.  \n"
                "Make sure the FastAPI backend is running (`uvicorn mailwright.main:app --reload`)."
            ),
        })
        return (
            history,
            _phase_badge(phase),
            thread_id, thread_id or "—",
            phase,
            template_id, template_id or "—",
            version_id, version_id or "—",
            "",
        )

    except Exception as exc:
        history.append({"role": "assistant", "content": f"⚠️ Unexpected error: {exc}"})
        return (
            history,
            _phase_badge(phase),
            thread_id, thread_id or "—",
            phase,
            template_id, template_id or "—",
            version_id, version_id or "—",
            "",
        )

    reply        = data.get("reply", "")
    new_tid      = data.get("thread_id") or thread_id
    new_phase    = data.get("phase", phase)
    new_tmpl     = data.get("template_id") or template_id
    new_ver      = data.get("current_version_id") or version_id
    html_url     = data.get("html_preview_url")

    if html_url:
        base     = api_base.rstrip("/")
        full_url = f"{base}{html_url}"
        reply   += (
            f"\n\n---\n"
            f"🔗 **[Open HTML preview]({full_url})**  \n"
            f"`{full_url}`"
        )

    history.append({"role": "assistant", "content": reply})

    return (
        history,
        _phase_badge(new_phase),
        new_tid,  new_tid  or "—",
        new_phase,
        new_tmpl, new_tmpl or "—",
        new_ver,  new_ver  or "—",
        "",
    )


def new_conversation():
    return (
        [],
        _phase_badge("gathering"),
        None, "—",
        "gathering",
        None, "—",
        None, "—",
        "",
    )


# ── Layout ─────────────────────────────────────────────────────────────────

_CSS = """
footer { display: none !important; }
#send-btn { min-width: 90px; }
"""

with gr.Blocks(
    title="mailwright — Email Template Assistant",
    theme=gr.themes.Soft(primary_hue="blue"),
    css=_CSS,
) as demo:

    # hidden state
    s_thread_id   = gr.State(None)
    s_phase       = gr.State("gathering")
    s_template_id = gr.State(None)
    s_version_id  = gr.State(None)

    gr.Markdown(
        "# ✉️  mailwright — Email Template Assistant\n"
        "Chat naturally to **create**, **revise**, and **approve** marketing email templates."
    )

    with gr.Row(equal_height=True):

        # ── Chat column ───────────────────────────────────────────────────
        with gr.Column(scale=4):
            chatbot = gr.Chatbot(
                label="",
                height=500,
                type="messages",          # Gradio 6 messages format
                show_copy_button=True,
                render_markdown=True,
            )

            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="Type your message and press Enter…",
                    show_label=False,
                    scale=5,
                    autofocus=True,
                    lines=1,
                )
                send_btn = gr.Button(
                    "Send ➤",
                    variant="primary",
                    scale=1,
                    elem_id="send-btn",
                )

            gr.Examples(
                examples=[
                    ["I want to create a welcome email for my SaaS product"],
                    ["Create a summer sale email for a fashion brand"],
                    ["I need a product launch email for a new mobile app"],
                    ["Build a newsletter for a coffee subscription service"],
                ],
                inputs=msg_input,
                label="💡 Quick starts — click to fill, then press Send",
            )

        # ── Info sidebar ─────────────────────────────────────────────────
        with gr.Column(scale=1, min_width=220):
            gr.Markdown("### 📋 Session")

            phase_html    = gr.HTML(_phase_badge("gathering"))

            d_thread_id   = gr.Textbox(label="Thread ID",       value="—", interactive=False, max_lines=1)
            d_template_id = gr.Textbox(label="Template ID",     value="—", interactive=False, max_lines=1)
            d_version_id  = gr.Textbox(label="Current Version", value="—", interactive=False, max_lines=1)

            gr.Markdown("---")

            api_base_input = gr.Textbox(
                label="🔌 API Base URL",
                value=DEFAULT_API_BASE,
                interactive=True,
                max_lines=1,
            )

            new_btn = gr.Button("🔄 New Conversation", variant="secondary")

            gr.Markdown(
                "---\n"
                "**Phases**\n"
                "- 🔍 mailwright gathers info\n"
                "- 👁️ Review the template\n"
                "- ✅ Approved & final\n\n"
                "**Tips**\n"
                "- Request changes freely\n"
                "- Say *'approve'* to finalise\n"
                "- Click preview link to view HTML\n"
            )

    # ── Wiring ─────────────────────────────────────────────────────────────

    _inputs  = [msg_input, chatbot, s_thread_id, s_phase, s_template_id, s_version_id, api_base_input]
    _outputs = [
        chatbot,
        phase_html,
        s_thread_id, d_thread_id,
        s_phase,
        s_template_id, d_template_id,
        s_version_id, d_version_id,
        msg_input,
    ]

    send_btn.click(send_message, inputs=_inputs, outputs=_outputs)
    msg_input.submit(send_message, inputs=_inputs, outputs=_outputs)
    new_btn.click(new_conversation, inputs=[], outputs=_outputs)


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        share=False,
    )
