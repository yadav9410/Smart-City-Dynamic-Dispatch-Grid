"""Streamlit entrypoint for the Smart City Dynamic Dispatch Grid prototype."""

import streamlit as st

from smartcity.config import settings
from smartcity.safety import EMERGENCY_INSTRUCTIONS
from smartcity.ui.public_intake import render_public_intake, render_public_intake_limitations
from smartcity.operator_auth import maintain_operator_session
from smartcity.ui.operator_console import render_operator_console

st.set_page_config(
    page_title=settings.app_name,
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)

maintain_operator_session(st.session_state)

# A lightweight responsive theme built from native Streamlit components and CSS.
st.markdown(
    """
    <style>
    :root {
      --grid-teal: #5eead4;
      --grid-cyan: #67e8f9;
      --grid-ink: #07111f;
      --grid-panel: rgba(17, 30, 49, .78);
      --grid-border: rgba(148, 163, 184, .20);
      --grid-muted: #a9b8cc;
    }
    .stApp {
      background:
        radial-gradient(ellipse at 8% 0%, rgba(20, 184, 166, .12), transparent 32rem),
        radial-gradient(ellipse at 98% 10%, rgba(59, 130, 246, .10), transparent 28rem),
        #080f1b;
    }
    .block-container {max-width: 1180px; padding-top: 1.65rem; padding-bottom: 3rem;}
    section[data-testid="stSidebar"] {
      background: linear-gradient(180deg, #0d1828 0%, #0a1220 100%);
      border-right: 1px solid rgba(148, 163, 184, .14);
    }
    .brand-lockup {display:flex; align-items:center; gap:.75rem; padding:.15rem 0 .75rem 0;}
    .brand-icon {
      display:flex; align-items:center; justify-content:center; width:2.65rem; height:2.65rem;
      border-radius: .9rem; background:linear-gradient(135deg,#0f766e,#155e75);
      border:1px solid rgba(94,234,212,.45); font-size:1.35rem;
      box-shadow:0 8px 28px rgba(20,184,166,.12);
    }
    .brand-title {font-size:1.02rem; line-height:1.15; font-weight:800; color:#f1f5f9;}
    .brand-subtitle {font-size:.76rem; color:#94a3b8; margin-top:.22rem;}
    .hero-shell {
      position:relative; overflow:hidden; padding:2rem 2.1rem 1.85rem;
      border:1px solid rgba(94,234,212,.22); border-radius:24px; margin:.25rem 0 1.25rem;
      background:linear-gradient(120deg,rgba(13,148,136,.18) 0%,rgba(15,23,42,.94) 49%,rgba(30,64,175,.20) 100%);
      box-shadow:0 24px 70px rgba(0,0,0,.20);
    }
    .hero-shell:after {
      content:""; position:absolute; right:-4.5rem; top:-6rem; width:18rem; height:18rem;
      border:1px solid rgba(103,232,249,.15); border-radius:50%;
      box-shadow:0 0 0 2rem rgba(103,232,249,.025),0 0 0 4rem rgba(103,232,249,.02);
      pointer-events:none;
    }
    .hero-eyebrow {
      display:inline-flex; align-items:center; gap:.45rem; color:#99f6e4; font-weight:750;
      text-transform:uppercase; letter-spacing:.105em; font-size:.73rem;
      border:1px solid rgba(94,234,212,.25); background:rgba(13,148,136,.10);
      border-radius:999px; padding:.38rem .7rem;
    }
    .hero-eyebrow-dot {display:inline-block; height:.42rem; width:.42rem; border-radius:50%; background:#5eead4; box-shadow:0 0 12px rgba(94,234,212,.7);}
    .hero-title {font-size:clamp(2rem,4.2vw,3.5rem); line-height:1.02; letter-spacing:-.04em; font-weight:850; margin:1rem 0 .8rem; color:#f8fafc; position:relative; z-index:1;}
    .hero-title span {color:#5eead4;}
    .hero-copy {max-width:800px; color:#cbd5e1; font-size:1.02rem; line-height:1.65; margin:0; position:relative; z-index:1;}
    .hero-pills {display:flex; flex-wrap:wrap; gap:.55rem; margin-top:1.25rem; position:relative; z-index:1;}
    .hero-pill {display:inline-block; padding:.42rem .68rem; color:#dbeafe; font-size:.78rem; border-radius:999px; background:rgba(15,23,42,.62); border:1px solid rgba(148,163,184,.22);}
    .section-kicker {color:#5eead4; text-transform:uppercase; letter-spacing:.12em; font-size:.72rem; font-weight:800; margin-bottom:.2rem;}
    .section-title {font-size:1.45rem; color:#f8fafc; font-weight:800; letter-spacing:-.025em; margin:.1rem 0 .45rem;}
    .section-description {color:#a9b8cc; margin-bottom:1rem;}
    .step-card {
      min-height:130px; border:1px solid var(--grid-border); background:var(--grid-panel);
      border-radius:16px; padding:1rem 1.05rem; margin-bottom:.6rem;
    }
    .step-num {font-size:.72rem; font-weight:800; letter-spacing:.09em; color:#5eead4; text-transform:uppercase;}
    .step-title {font-size:1rem; color:#f1f5f9; font-weight:750; margin:.35rem 0 .2rem;}
    .step-copy {font-size:.86rem; line-height:1.5; color:#a9b8cc;}
    .emergency-banner {
      display:flex; flex-wrap:wrap; align-items:center; gap:.55rem 1rem;
      border:1px solid rgba(248,113,113,.35); border-left:4px solid #f87171;
      background:linear-gradient(90deg,rgba(127,29,29,.28),rgba(69,10,10,.16));
      border-radius:13px; padding:.9rem 1.05rem; margin:.85rem 0 .8rem; color:#fecaca; line-height:1.5;
    }
    .emergency-banner strong {color:#fff1f2;}
    .prototype-banner {
      border:1px solid rgba(94,234,212,.19); background:rgba(13,148,136,.075);
      border-radius:12px; padding:.85rem 1rem; color:#cbd5e1; line-height:1.55; margin-bottom:1rem;
    }
    .service-note {
      border:1px solid rgba(148,163,184,.20); background:rgba(30,41,59,.42);
      border-radius:11px; padding:.72rem .9rem; color:#cbd5e1; font-size:.88rem;
      line-height:1.5; margin:.5rem 0 .8rem;
    }
    .service-note strong {color:#e2e8f0;}
    .location-step-heading {margin-top:.2rem;}
    .required-chip {
      display:inline-block; vertical-align:middle; margin-left:.45rem; padding:.20rem .5rem;
      border-radius:999px; color:#99f6e4; background:rgba(13,148,136,.14);
      border:1px solid rgba(94,234,212,.30); font-size:.63rem; letter-spacing:.09em;
    }
    .location-action-title {font-size:1.02rem; font-weight:800; color:#f1f5f9; margin:.1rem 0 .25rem;}
    .location-action-copy {font-size:.88rem; color:#a9b8cc; line-height:1.5; margin-bottom:.55rem;}
    .info-card {border:1px solid var(--grid-border); background:rgba(15,23,42,.58); border-radius:15px; padding:1rem 1.05rem; min-height:140px;}
    .info-card-title {color:#e2e8f0; font-weight:800; margin-bottom:.4rem;}
    .info-card-copy {color:#a9b8cc; font-size:.88rem; line-height:1.55;}
    .footer-line {border-top:1px solid rgba(148,163,184,.16); margin-top:1.8rem; padding-top:1rem; color:#8292a8; font-size:.78rem; text-align:center;}
    div.stButton > button, div[data-testid="stFormSubmitButton"] button {
      border-radius:11px; font-weight:700; min-height:2.65rem; transition:all .15s ease;
    }
    div.stButton > button[kind="primary"], div[data-testid="stFormSubmitButton"] button[kind="primary"] {
      background:linear-gradient(105deg,#0f9f92,#0e7490); color:white; border:1px solid rgba(94,234,212,.38);
    }
    div.stButton > button[kind="primary"]:hover, div[data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
      border-color:#5eead4; filter:brightness(1.08);
    }
    div[data-testid="stForm"] {border-color:rgba(148,163,184,.23); border-radius:16px;}
    div[data-testid="stExpander"] {border-color:rgba(148,163,184,.2); border-radius:12px;}
    [data-testid="stMetric"] {background:rgba(15,23,42,.52); border:1px solid var(--grid-border); padding:.9rem 1rem; border-radius:13px;}
    @media (max-width: 700px) {
      .block-container {padding-left:1rem; padding-right:1rem; padding-top:1rem;}
      .hero-shell {padding:1.3rem 1.15rem; border-radius:18px;}
      .hero-copy {font-size:.94rem;}
      .step-card {min-height:0;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        """
        <div class="brand-lockup">
          <div class="brand-icon">🚨</div>
          <div>
            <div class="brand-title">Dispatch Grid</div>
            <div class="brand-subtitle">Smart-city coordination lab</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="hero-pills" style="margin:0 0 .7rem 0"><span class="hero-pill">PUBLIC PROTOTYPE</span><span class="hero-pill">SIMULATION ONLY</span></div>',
        unsafe_allow_html=True,
    )
    selected_view = st.radio(
        "Navigate",
        ["Public reporting", "Operator console"],
        index=0,
        key="app_view",
        label_visibility="visible",
    )
    st.divider()
    st.markdown(
        '<div class="service-note"><strong>Not an emergency channel</strong><br>Requests are stored only when configured and consented to. No real responders are contacted.</div>',
        unsafe_allow_html=True,
    )
    st.caption("A reference code is a storage receipt—not a dispatch confirmation.")

if selected_view == "Operator console":
    st.markdown(
        '<div class="section-kicker">Restricted workspace</div><div class="section-title">Operator console</div>',
        unsafe_allow_html=True,
    )
    render_operator_console()
    st.markdown(
        '<div class="footer-line">Phase 16 · Prototype only · No real dispatch or emergency-service integration</div>',
        unsafe_allow_html=True,
    )
    st.stop()

st.markdown(
    """
    <div class="hero-shell">
      <div class="hero-eyebrow"><span class="hero-eyebrow-dot"></span> AI-assisted coordination · Public prototype</div>
      <div class="hero-title">The Smart City<br><span>Dynamic Dispatch Grid</span></div>
      <p class="hero-copy">A demonstration interface for recording an incident description, adding a required location, and reviewing clearly labeled simulated resources. No real emergency response is initiated.</p>
      <div class="hero-pills">
        <span class="hero-pill">✦ Text and voice input</span>
        <span class="hero-pill">⌖ Required location step</span>
        <span class="hero-pill">◈ Simulated map preview</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f'<div class="emergency-banner"><span style="font-size:1.25rem">☎</span><div><strong>Immediate danger?</strong> {EMERGENCY_INSTRUCTIONS}</div></div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="section-kicker" style="margin-top:1.55rem">Submit a demonstration report</div>',
    unsafe_allow_html=True,
)
render_public_intake()

st.markdown('<div class="section-kicker" style="margin-top:1.6rem">Built for transparent testing</div><div class="section-title">How this prototype behaves</div>', unsafe_allow_html=True)
left, middle, right = st.columns(3, gap="medium")
with left:
    st.markdown(
        '<div class="info-card"><div class="info-card-title">01 · Record</div><div class="info-card-copy">Describe a fictional incident. Voice transcription is optional, and transcripts can be reviewed before submission.</div></div>',
        unsafe_allow_html=True,
    )
with middle:
    st.markdown(
        '<div class="info-card"><div class="info-card-title">02 · Review</div><div class="info-card-copy">Add a current location, map pin, or landmark, then confirm location storage separately from report and AI consent.</div></div>',
        unsafe_allow_html=True,
    )
with right:
    st.markdown(
        '<div class="info-card"><div class="info-card-title">03 · Preview</div><div class="info-card-copy">Explore an optional AI assessment and synthetic map layers. They are demonstrations, not real dispatch.</div></div>',
        unsafe_allow_html=True,
    )

st.markdown(
    '<div class="prototype-banner" style="margin-top:1.8rem"><strong>Prototype boundary</strong> &nbsp; This demo does not contact emergency services, reserve real resources, or dispatch responders. Do not submit real sensitive incident information.</div>',
    unsafe_allow_html=True,
)
render_public_intake_limitations()

st.markdown(
    '<div class="footer-line">The Smart City Dynamic Dispatch Grid · Phase 16 · AI-assisted demo · No real emergency-service integration</div>',
    unsafe_allow_html=True,
)
