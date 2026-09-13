"""Shared visual components for the research platform."""

from __future__ import annotations

import base64
import html
import mimetypes
from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).resolve().parent
ASSET_DIR = APP_DIR / "assets"
CONTENT_DIR = APP_DIR / "content"


def data_uri(path: Path) -> str:
    """Encode a local image so it renders reliably on Community Cloud."""

    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def editable_markdown(filename: str, fallback: str) -> str:
    """Load page copy from a Markdown file that can be edited on GitHub."""

    path = CONTENT_DIR / filename
    return path.read_text(encoding="utf-8") if path.exists() else fallback


def apply_global_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ua-green: #275d38; --ua-dark: #173d27; --ua-gold: #ffdb05;
            --ink: #14251c; --muted: #5b6961; --line: #d8e2da;
        }
        .stApp { background: linear-gradient(180deg, #f1f5ef 0, #fff 30rem); }
        [data-testid="stHeader"] { background: rgba(241,245,239,.93); }
        [data-testid="stSidebar"] { background: #f2f6f1; }
        .block-container { max-width: 1200px; padding-top: 1.35rem; padding-bottom: 4rem; }
        .platform-hero, .project-hero {
            position: relative; overflow: hidden; padding: 1.55rem 1.75rem 1.7rem;
            background: rgba(255,255,255,.96); border: 1px solid #d4e0d7;
            border-top: 7px solid var(--ua-green); border-radius: 20px;
            box-shadow: 0 14px 36px rgba(20,49,32,.08);
        }
        .platform-hero::after, .project-hero::after {
            content: ""; position: absolute; width: 190px; height: 190px;
            right: -72px; top: -92px; border-radius: 50%;
            background: var(--ua-gold); opacity: .76;
        }
        .brand-logo { width: 245px; max-width: 58%; height: auto; display: block; margin-bottom: 1.1rem; }
        .eyebrow { color: var(--ua-green); font-weight: 900; letter-spacing: .11em;
            text-transform: uppercase; font-size: .76rem; }
        .platform-hero h1, .project-hero h1 { color: var(--ink); font-family: Georgia, serif;
            font-weight: 500; font-size: clamp(2rem,4vw,3.35rem); line-height: 1.06;
            margin: .38rem 0 .66rem; max-width: 900px; }
        .platform-hero p, .project-hero p { color: var(--muted); font-size: 1.02rem;
            max-width: 850px; margin: 0; }
        .credit-line { color: var(--ink); font-size: .92rem; font-weight: 800; margin-top: 1rem; }
        .people-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr));
            gap: 1rem; margin: 1.1rem 0 1.7rem; }
        .person-card { display: flex; align-items: center; gap: 1rem; padding: 1rem;
            background: #fff; border: 1px solid var(--line); border-radius: 16px;
            box-shadow: 0 6px 18px rgba(20,49,32,.05); }
        .person-card img { width: 100px; height: 100px; flex: 0 0 100px; object-fit: cover;
            border-radius: 50%; border: 4px solid #fff; outline: 3px solid var(--ua-green); }
        .person-card h3 { color: var(--ink); font-size: 1.13rem; margin: 0 0 .25rem; }
        .person-card p { color: var(--muted); margin: 0; font-size: .9rem; line-height: 1.38; }
        .person-card .person-contact { margin-top: .45rem; }
        .person-card a { color: var(--ua-green); font-weight: 800; text-decoration: none; }
        .person-card a:hover { text-decoration: underline; }
        .section-label { color: var(--ua-green); font-size: .78rem; font-weight: 900;
            letter-spacing: .1em; text-transform: uppercase; margin-top: 1.5rem; }
        .app-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr));
            gap: 1rem; margin: 1rem 0 1.8rem; }
        .app-card { display: flex; flex-direction: column; min-height: 265px; padding: 1.2rem;
            color: var(--ink) !important; text-decoration: none !important; background: #fff;
            border: 1px solid var(--line); border-top: 5px solid var(--ua-green);
            border-radius: 17px; box-shadow: 0 8px 24px rgba(20,49,32,.07);
            transition: transform .18s ease, box-shadow .18s ease; }
        .app-card:hover { transform: translateY(-4px); box-shadow: 0 15px 32px rgba(20,49,32,.14); }
        .app-number { display: inline-grid; place-items: center; width: 46px; height: 46px;
            color: var(--ua-dark); background: var(--ua-gold); border-radius: 13px;
            font-weight: 950; font-size: 1.05rem; }
        .app-card h3 { font-size: 1.25rem; line-height: 1.2; margin: 1rem 0 .55rem; }
        .app-card p { color: var(--muted); font-size: .9rem; line-height: 1.48; margin: 0; }
        .app-link { margin-top: auto; padding-top: 1rem; color: var(--ua-green);
            font-weight: 900; font-size: .92rem; }
        .external-cta {
            display: flex; align-items: center; justify-content: space-between; gap: 1rem;
            margin: 1.25rem 0; padding: 1.15rem 1.3rem; color: #fff !important;
            text-decoration: none !important; background: linear-gradient(120deg,#1f4d30,#173d27);
            border: 3px solid var(--ua-gold); border-radius: 17px;
            box-shadow: 0 12px 28px rgba(20,49,32,.18); }
        .external-cta strong { display: block; color: #fff; font-size: 1.32rem; }
        .external-cta span { color: #dfece2; font-size: .9rem; }
        .external-cta b { color: var(--ua-gold); font-size: 1.8rem; }
        .notice { margin: 1rem 0; padding: .9rem 1rem; color: #405047; background: #eef4ef;
            border-left: 4px solid var(--ua-green); border-radius: 6px; }
        @media (max-width: 850px) { .app-grid { grid-template-columns: 1fr; } }
        @media (max-width: 700px) {
            .people-grid { grid-template-columns: 1fr; }
            .person-card img { width: 84px; height: 84px; flex-basis: 84px; }
            .platform-hero, .project-hero { padding: 1.2rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_platform_hero() -> None:
    logo = data_uri(ASSET_DIR / "university_of_alberta_logo.svg")
    st.markdown(
        f"""
        <section class="platform-hero">
          <img class="brand-logo" src="{logo}" alt="University of Alberta">
          <div class="eyebrow">Pipeline integrity research</div>
          <h1>Pipeline Integrity Research Platform</h1>
          <p>A unified gateway to reliability, inspection, maintenance, and
          value-of-information tools developed from doctoral research.</p>
          <div class="credit-line">Developed by Mohammadali Ameri and Yong Li</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_team(show_contacts: bool = False) -> None:
    mohammadali = data_uri(ASSET_DIR / "mohammadali_ameri.png")
    yong = data_uri(ASSET_DIR / "yong_li.png")
    mohammadali_contact = (
        '<p class="person-contact"><a href="mailto:amerifar@ualberta.ca">'
        'amerifar@ualberta.ca</a><br><a href="https://www.linkedin.com/in/'
        'mohammad-ali-ameri" target="_blank" rel="noopener">LinkedIn profile</a></p>'
        if show_contacts
        else ""
    )
    yong_contact = (
        '<p class="person-contact"><a href="mailto:yong9@ualberta.ca">'
        'yong9@ualberta.ca</a></p>'
        if show_contacts
        else ""
    )
    st.markdown(
        f"""
        <section class="people-grid" aria-label="Platform developers">
          <article class="person-card">
            <img src="{mohammadali}" alt="Mohammadali Ameri">
            <div><h3>Mohammadali Ameri</h3><p>PhD researcher and developer<br>University of Alberta</p>{mohammadali_contact}</div>
          </article>
          <article class="person-card">
            <img src="{yong}" alt="Yong Li">
            <div><h3>Yong Li</h3><p>Associate Professor and co-developer<br>University of Alberta</p>{yong_contact}</div>
          </article>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_project_hero(kicker: str, title: str, description: str) -> None:
    st.markdown(
        f"""
        <section class="project-hero">
          <div class="eyebrow">{html.escape(kicker)}</div>
          <h1>{html.escape(title)}</h1>
          <p>{html.escape(description)}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_external_cta(url: str, title: str, detail: str) -> None:
    st.markdown(
        f"""
        <a class="external-cta" href="{html.escape(url, quote=True)}" target="_self">
          <div><strong>{html.escape(title)}</strong><span>{html.escape(detail)}</span></div>
          <b aria-hidden="true">→</b>
        </a>
        """,
        unsafe_allow_html=True,
    )
