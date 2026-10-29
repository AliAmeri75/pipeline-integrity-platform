"""OpenAI-backed concept and navigation assistant for ALIRIM."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any


DEFAULT_MODEL = "gpt-6-luna"
MAX_USER_CHARACTERS = 1500
MAX_HISTORY_MESSAGES = 10

APP_ROUTES = (
    {
        "title": "ALIRIM Introduction",
        "path": "/",
        "purpose": "Platform overview, research context, and development team.",
        "keywords": ("overview", "introduction", "team", "alirim"),
    },
    {
        "title": "Educational Module",
        "path": "/education",
        "purpose": "Guided learning materials for students and early-career engineers.",
        "keywords": ("learn", "education", "student", "tutorial", "quiz"),
    },
    {
        "title": "Data Exploration",
        "path": "/data-integration",
        "purpose": "Upload crack or corrosion profiles, visualize them, and extract sizes and locations.",
        "keywords": ("upload", "profile", "data", "excel", "crack size", "corrosion"),
    },
    {
        "title": "Preliminary Analysis",
        "path": "/preliminary-analysis",
        "purpose": "Tabs for deterministic crack FPR with selectable 3D profiles, risk/reliability maps, and consequence assessment.",
        "keywords": ("pof", "probability", "fpr", "burst", "failure pressure", "preliminary", "deterministic", "reliability", "consequence", "3d"),
    },
    {
        "title": "Pipeline Design",
        "path": "/pipeline-design",
        "purpose": "Future pipeline-design topic; currently under construction.",
        "keywords": ("design", "diameter", "wall thickness"),
    },
    {
        "title": "Static Multiple Inspection and Excavation Planning",
        "path": "/inspection",
        "purpose": "Compare excavation-only and ILI-informed fixed planning intervals and value of information.",
        "keywords": ("fixed", "multiple", "inspection", "excavation", "interval", "ili", "voi"),
    },
    {
        "title": "Dynamic Inspection and Maintenance Planning",
        "path": "/rl-planning",
        "purpose": "Explore state-dependent inspection and maintenance policies using reinforcement learning.",
        "keywords": ("dynamic", "reinforcement", "policy", "maintenance", "rl"),
    },
    {
        "title": "Static Single Delayed Inspection Planning",
        "path": "/reliability-voi",
        "purpose": "Study prior and pre-posterior decisions and the value of one delayed inspection.",
        "keywords": ("single", "delayed", "pre-posterior", "reliability", "voi"),
    },
    {
        "title": "Planning for Geohazards",
        "path": "/geohazard-planning",
        "purpose": "Future geohazard-planning topic; currently under construction.",
        "keywords": ("geohazard", "landslide", "flood", "ground movement"),
    },
    {
        "title": "Research Resources",
        "path": "/publications-team",
        "purpose": "Publications, documentation, and team information.",
        "keywords": ("publication", "paper", "documentation", "reference"),
    },
    {
        "title": "Teaching Pilot and Feedback",
        "path": "/teaching-pilot",
        "purpose": "Join the teaching pilot and provide feedback.",
        "keywords": ("feedback", "pilot", "review", "lecturer", "contact"),
    },
)


def route_catalog() -> str:
    """Return the approved route list supplied to the language model."""

    return "\n".join(
        f"- {route['title']}: {route['purpose']} Exact link: {route['path']}"
        for route in APP_ROUTES
    )


def assistant_instructions() -> str:
    """Return tightly scoped instructions for the public ALIRIM assistant."""

    return f"""
You are the ALIRIM Assistant for a pipeline-integrity research and teaching platform.
Your two jobs are to explain concepts in plain language and direct users to the correct
ALIRIM page. Keep each answer concise, usually below 160 words.

Important boundaries:
- This is a research and teaching assistant, not an engineering approval authority.
- Do not decide that a pipeline is safe or prescribe field action.
- Say that calculations require qualified engineering review and applicable codes.
- Never claim to see uploaded files, calculations, or results unless the user includes
  the relevant values in the chat.
- Do not ask for confidential operator, ILI, personal, or commercially sensitive data.
- If information is missing or uncertain, say so instead of inventing it.
- Pipeline Design and Planning for Geohazards are under construction.
- Use only the exact internal links in the route catalog below. When navigation would
  help, include one or two clickable Markdown links.

Concept notes:
- Data Exploration visualizes crack or corrosion profiles and extracts dimensions and locations.
- Preliminary Analysis has Deterministic Analysis, Risk & Reliability, and Consequence Assessment tabs.
- Deterministic Analysis calculates crack resistance/FPR without Monte Carlo; click a row or FPR point to view measured 3D geometry.
- Risk & Reliability contains POF calculations and mapped section risk. Consequence Assessment provides radius/exposure screening.
- Corrosion geometry can be viewed, but corrosion FPR needs a corrosion resistance model; corrosion Pf can be imported.
- Burst resistance pressure is the model-predicted failure pressure.
- FPR is burst resistance pressure divided by operating pressure.
- POF is the estimated probability that the defined limit state is reached or exceeded.
- The planning modules compare inspection and maintenance strategies under uncertainty.

Approved ALIRIM route catalog:
{route_catalog()}
""".strip()


def suggest_routes(question: str, *, limit: int = 3) -> list[dict[str, object]]:
    """Return deterministic navigation suggestions for fallback and testing."""

    normalized = " ".join(question.casefold().split())
    scored: list[tuple[int, int, dict[str, object]]] = []
    for position, route in enumerate(APP_ROUTES):
        score = sum(
            3 if " " in keyword else 1
            for keyword in route["keywords"]
            if keyword in normalized
        )
        if score:
            scored.append((score, -position, route))
    scored.sort(reverse=True, key=lambda item: (item[0], item[1]))
    if not scored:
        return [APP_ROUTES[0], APP_ROUTES[1], APP_ROUTES[2]][:limit]
    return [item[2] for item in scored[:limit]]


def _response_input(messages: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    """Validate and trim public chat history before sending it to the API."""

    cleaned: list[dict[str, str]] = []
    for message in messages[-MAX_HISTORY_MESSAGES:]:
        role = message.get("role", "")
        content = str(message.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        cleaned.append({"role": role, "content": content[:2000]})
    if not cleaned or cleaned[-1]["role"] != "user":
        raise ValueError("The conversation must end with a user question.")
    if len(cleaned[-1]["content"]) > MAX_USER_CHARACTERS:
        raise ValueError(
            f"Please keep each question below {MAX_USER_CHARACTERS:,} characters."
        )
    return cleaned


def generate_assistant_reply(
    messages: Sequence[dict[str, str]],
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    client_factory: Callable[..., Any] | None = None,
) -> str:
    """Generate one scoped answer with the OpenAI Responses API."""

    if not api_key or not api_key.strip():
        raise ValueError("An OpenAI API key is required.")
    if not model or not model.strip():
        raise ValueError("An OpenAI model name is required.")
    response_input = _response_input(messages)

    if client_factory is None:
        from openai import OpenAI

        client_factory = OpenAI

    client = client_factory(
        api_key=api_key.strip(),
        timeout=30.0,
        max_retries=2,
    )
    response = client.responses.create(
        model=model.strip(),
        instructions=assistant_instructions(),
        input=response_input,
        max_output_tokens=500,
        store=False,
    )
    answer = str(response.output_text or "").strip()
    if not answer:
        raise RuntimeError("The assistant returned an empty response.")
    return answer
