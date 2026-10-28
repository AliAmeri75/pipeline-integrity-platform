"""Public ALIRIM concept and navigation assistant."""

from __future__ import annotations

import logging
import os

import streamlit as st

from chatbot_service import (
    DEFAULT_MODEL,
    MAX_USER_CHARACTERS,
    generate_assistant_reply,
    suggest_routes,
)
from platform_ui import render_project_hero


LOGGER = logging.getLogger(__name__)
MESSAGE_STATE_KEY = "alirim_assistant_messages"
USAGE_STATE_KEY = "alirim_assistant_request_count"
DEFAULT_MESSAGE_LIMIT = 12


def _setting(name: str, default: str | None = None) -> str | None:
    """Read a deployment secret first, then an environment variable."""

    try:
        value = st.secrets.get(name)
    except (FileNotFoundError, KeyError):
        value = None
    return str(value) if value is not None else os.getenv(name, default)


def _message_limit() -> int:
    try:
        return max(1, min(int(_setting("ALIRIM_CHAT_MESSAGE_LIMIT", "12")), 50))
    except (TypeError, ValueError):
        return DEFAULT_MESSAGE_LIMIT


def _route_fallback(question: str) -> str:
    routes = suggest_routes(question)
    links = "\n".join(
        f"- [{route['title']}]({route['path']}): {route['purpose']}" for route in routes
    )
    return "The AI response is temporarily unavailable. These pages may help:\n\n" + links


render_project_hero(
    "Concept and Navigation Help",
    "ALIRIM Assistant",
    "Ask a pipeline-integrity concept question or describe what you want to do, and the assistant will guide you to the relevant module.",
)

st.markdown(
    """
    <div class="notice"><strong>Research and teaching support only.</strong> Do not enter
    confidential operator, ILI, personal, or commercially sensitive information. Answers
    may be incomplete and do not replace engineering review, applicable codes, or regulatory
    requirements.</div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    "**Quick links:** [Data Preparation](/data-integration) · "
    "[Preliminary Analysis](/preliminary-analysis) · "
    "[Inspection Planning](/inspection) · [Education](/education)"
)

api_key = _setting("OPENAI_API_KEY")
model = _setting("OPENAI_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL

if not api_key:
    st.warning(
        "The OpenAI connection has not been configured yet. Quick navigation is still available below."
    )
    with st.expander("Deployment setup for the app owner"):
        st.markdown(
            "1. Create an OpenAI project API key.\n"
            "2. In Streamlit Community Cloud, open **Manage app → Settings → Secrets**.\n"
            "3. Add `OPENAI_API_KEY` and `OPENAI_MODEL = \"gpt-6-luna\"`.\n"
            "4. Save the secrets and reboot the app.\n\n"
            "Never place the real key in GitHub."
        )
    navigation_question = st.text_input(
        "What do you want to find?",
        placeholder="Example: I want to estimate POF for crack profiles",
        max_chars=MAX_USER_CHARACTERS,
    )
    if navigation_question:
        st.markdown("**Suggested pages**")
        for route in suggest_routes(navigation_question):
            st.markdown(f"- [{route['title']}]({route['path']}): {route['purpose']}")
    st.stop()

if MESSAGE_STATE_KEY not in st.session_state:
    st.session_state[MESSAGE_STATE_KEY] = [
        {
            "role": "assistant",
            "content": (
                "Hello—I can explain ALIRIM concepts and help you find the right page. "
                "For example, ask **What is FPR?** or **Where do I upload crack profiles?**"
            ),
        }
    ]
if USAGE_STATE_KEY not in st.session_state:
    st.session_state[USAGE_STATE_KEY] = 0

header_columns = st.columns([4, 1])
header_columns[0].caption(f"Powered by the OpenAI API · Model: {model}")
if header_columns[1].button("Clear chat", use_container_width=True):
    st.session_state[MESSAGE_STATE_KEY] = st.session_state[MESSAGE_STATE_KEY][:1]
    st.rerun()

for message in st.session_state[MESSAGE_STATE_KEY]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

message_limit = _message_limit()
remaining = message_limit - int(st.session_state[USAGE_STATE_KEY])
if remaining <= 0:
    st.warning(
        "This browser session has reached its question limit. The ALIRIM quick links "
        "remain available above."
    )

question = st.chat_input(
    "Ask about a concept or where to go in ALIRIM",
    max_chars=MAX_USER_CHARACTERS,
    disabled=remaining <= 0,
)

if question:
    st.session_state[USAGE_STATE_KEY] += 1
    st.session_state[MESSAGE_STATE_KEY].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                answer = generate_assistant_reply(
                    st.session_state[MESSAGE_STATE_KEY],
                    api_key=api_key,
                    model=model,
                )
            except Exception as error:  # API/network details stay in owner-only logs
                LOGGER.exception("ALIRIM Assistant request failed: %s", error)
                answer = _route_fallback(question)
        st.markdown(answer)
    st.session_state[MESSAGE_STATE_KEY].append(
        {"role": "assistant", "content": answer}
    )
    st.caption(f"{max(remaining - 1, 0)} questions remaining in this chat session.")
