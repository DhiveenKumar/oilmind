import streamlit as st
import requests
import os

st.set_page_config(
    page_title="Field AI Agent",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.markdown("""
<style>
    .stApp { background-color: #060d1f; }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0a1628 0%, #060d1f 100%);
        border-right: 1px solid #162040;
    }
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] .stMarkdown li {
        color: #8899bb !important;
        font-size: 0.82rem;
    }
    [data-testid="stSidebar"] h3 {
        color: #3d8ef0 !important;
        font-size: 0.68rem !important;
        letter-spacing: 0.14em !important;
        text-transform: uppercase !important;
        font-weight: 700 !important;
        margin-top: 1.8rem !important;
    }
    [data-testid="stSidebar"] .stButton button {
        background: #0a1628 !important;
        border: 1px solid #162040 !important;
        color: #8899bb !important;
        font-size: 0.76rem !important;
        border-radius: 8px !important;
        transition: all 0.2s !important;
        width: 100% !important;
        text-align: left !important;
        padding: 0.5rem 0.8rem !important;
    }
    [data-testid="stSidebar"] .stButton button:hover {
        border-color: #3d8ef0 !important;
        color: #3d8ef0 !important;
        background: #3d8ef008 !important;
    }
    .main .block-container {
        padding: 1.5rem 2.5rem !important;
        max-width: 1000px !important;
    }
    .hero {
        position: relative;
        border-radius: 20px;
        padding: 2.8rem 3rem;
        margin-bottom: 1.8rem;
        overflow: hidden;
        background: #0a1628;
        border: 1px solid #162040;
    }
    .hero::before {
        content: '';
        position: absolute;
        top: -60px; left: 50%;
        transform: translateX(-50%);
        width: 500px; height: 200px;
        background: radial-gradient(ellipse, #1a4fff22 0%, transparent 70%);
        pointer-events: none;
    }
    .hero::after {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent 0%, #3d8ef0 40%, #00d4ff 60%, transparent 100%);
    }
    .hero-eyebrow {
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: #3d8ef0;
        margin-bottom: 0.6rem;
    }
    .hero-title {
        font-size: 3rem;
        font-weight: 800;
        color: #ffffff;
        margin: 0;
        line-height: 1;
        letter-spacing: -0.03em;
    }
    .hero-title .accent { color: #3d8ef0; }
    .hero-title .accent2 { color: #00d4ff; }
    .hero-sub {
        color: #5a7099;
        font-size: 0.88rem;
        margin-top: 0.6rem;
        letter-spacing: 0.02em;
    }
    .hero-tags { margin-top: 1.2rem; }
    .hero-tag {
        display: inline-block;
        background: #3d8ef008;
        border: 1px solid #3d8ef030;
        color: #3d8ef0;
        font-size: 0.65rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        padding: 0.22rem 0.65rem;
        border-radius: 20px;
        margin-right: 0.4rem;
    }
    .hero-tag.cyan {
        background: #00d4ff08;
        border-color: #00d4ff30;
        color: #00d4ff;
    }
    .hero-icon {
        position: absolute;
        right: 2.5rem; top: 50%;
        transform: translateY(-50%);
        font-size: 5rem;
        opacity: 0.06;
        user-select: none;
    }
    .query-counter {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: #0a1628;
        border: 1px solid #162040;
        border-radius: 20px;
        padding: 0.3rem 0.8rem;
        font-size: 0.72rem;
        color: #3d8ef0;
        margin-bottom: 1rem;
    }
    .query-counter-dot {
        width: 6px; height: 6px;
        border-radius: 50%;
        background: #3d8ef0;
    }
    .stTextArea textarea {
        background: #0a1628 !important;
        border: 1px solid #162040 !important;
        border-radius: 12px !important;
        color: #c8d8f0 !important;
        font-size: 0.92rem !important;
        padding: 1rem 1.2rem !important;
        line-height: 1.6 !important;
        transition: border-color 0.2s !important;
    }
    .stTextArea textarea:focus {
        border-color: #3d8ef0 !important;
        box-shadow: 0 0 0 3px #3d8ef010 !important;
    }
    .stTextArea textarea::placeholder { color: #2a3a55 !important; }
    .stTextArea label {
        color: #3a5070 !important;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.1em !important;
        text-transform: uppercase !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1a4fff, #3d8ef0) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        font-size: 0.85rem !important;
        letter-spacing: 0.04em !important;
        padding: 0.65rem 1.5rem !important;
        box-shadow: 0 4px 20px #1a4fff30 !important;
        transition: all 0.2s !important;
    }
    .stButton > button[kind="primary"]:hover {
        box-shadow: 0 6px 28px #1a4fff50 !important;
        transform: translateY(-1px) !important;
    }
    .stButton > button:not([kind="primary"]) {
        background: #0a1628 !important;
        border: 1px solid #162040 !important;
        color: #5a7099 !important;
        border-radius: 10px !important;
        font-size: 0.82rem !important;
    }
    .typing-indicator {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        padding: 1rem 1.5rem;
        background: #0a1628;
        border: 1px solid #162040;
        border-radius: 12px;
        margin: 1rem 0;
        color: #3d8ef0;
        font-size: 0.82rem;
    }
    .typing-dots { display: flex; gap: 4px; }
    .typing-dot {
        width: 6px; height: 6px;
        border-radius: 50%;
        background: #3d8ef0;
        animation: bounce 1.2s ease-in-out infinite;
    }
    .typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes bounce {
        0%,80%,100% { transform: translateY(0); opacity: 0.4; }
        40% { transform: translateY(-6px); opacity: 1; }
    }
    .metric-row {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 0.8rem;
        margin: 1.2rem 0;
    }
    .metric-card {
        background: #0a1628;
        border: 1px solid #162040;
        border-radius: 12px;
        padding: 1rem 1rem 0.8rem;
        text-align: center;
        position: relative;
        overflow: hidden;
    }
    .metric-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, #1a4fff, #3d8ef0);
    }
    .metric-icon { font-size: 1.1rem; margin-bottom: 0.3rem; display: block; }
    .metric-label {
        color: #2a3a55;
        font-size: 0.62rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-bottom: 0.3rem;
    }
    .metric-value {
        color: #3d8ef0;
        font-size: 1.5rem;
        font-weight: 800;
        line-height: 1;
    }
    .metric-unit { color: #2a3a55; font-size: 0.65rem; margin-top: 0.2rem; }
    .badge {
        display: inline-block;
        padding: 0.25rem 0.8rem;
        border-radius: 20px;
        font-size: 0.65rem;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-top: 0.2rem;
    }
    .badge-simple {
        background: #0a2518;
        border: 1px solid #0f4a28;
        color: #2ecc71;
    }
    .badge-complex {
        background: #0a1628;
        border: 1px solid #1a4fff40;
        color: #3d8ef0;
    }
    .sec-header {
        color: #2a3a55;
        font-size: 0.65rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        margin: 1.5rem 0 0.7rem;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .sec-header::after {
        content: '';
        flex: 1;
        height: 1px;
        background: #0f1e35;
    }
    .answer-box {
        background: #0a1628;
        border: 1px solid #162040;
        border-left: 3px solid #3d8ef0;
        border-radius: 0 12px 12px 0;
        padding: 1.5rem 1.8rem;
        color: #b8cce8;
        font-size: 0.9rem;
        line-height: 1.85;
    }
    .answer-box strong { color: #e0eeff; }
    .sources-wrap {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin-top: 0.5rem;
    }
    .source-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: #0a1628;
        border: 1px solid #162040;
        border-radius: 8px;
        padding: 0.35rem 0.8rem;
        font-size: 0.73rem;
        color: #5a7099;
    }
    .source-doc {
        color: #3d8ef0;
        font-weight: 700;
        font-size: 0.7rem;
    }
    .source-page {
        background: #162040;
        color: #3d8ef0;
        font-size: 0.62rem;
        font-weight: 700;
        padding: 0.1rem 0.4rem;
        border-radius: 4px;
    }
    .trace-step {
        display: flex;
        gap: 0.8rem;
        padding: 0.5rem 0;
        border-bottom: 1px solid #0a1628;
        font-size: 0.8rem;
        color: #3a5070;
        align-items: flex-start;
    }
    .trace-dot {
        width: 6px; height: 6px;
        border-radius: 50%;
        background: #3d8ef0;
        margin-top: 0.3rem;
        flex-shrink: 0;
    }
    .empty-state {
        text-align: center;
        padding: 3rem 2rem;
    }
    .empty-icon { font-size: 3rem; margin-bottom: 1rem; opacity: 0.15; }
    .empty-title {
        color: #2a3a55;
        font-size: 0.9rem;
        font-weight: 600;
        margin-bottom: 0.4rem;
    }
    .empty-sub { color: #1e2d45; font-size: 0.8rem; line-height: 1.6; }
    .status-row {
        display: flex;
        align-items: center;
        color: #3a5070;
        font-size: 0.76rem;
        padding: 0.25rem 0;
        gap: 0.5rem;
    }
    .sdot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
    .sdot-ok { background: #2ecc71; }
    .sdot-err { background: #e74c3c; }
    .footer {
        text-align: center;
        color: #0f1e35;
        font-size: 0.65rem;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        padding: 2rem 0 0.5rem;
    }
    hr { border-color: #0f1e35 !important; margin: 1rem 0 !important; }
    .stSpinner > div { border-top-color: #3d8ef0 !important; }
</style>
""", unsafe_allow_html=True)

# Session state
if "run_query" not in st.session_state:
    st.session_state.run_query = ""
if "query_count" not in st.session_state:
    st.session_state.query_count = 0
if "last_result" not in st.session_state:
    st.session_state.last_result = None

# Sidebar
with st.sidebar:
    st.markdown("""
    <div style="padding:1rem 0 1.5rem;border-bottom:1px solid #162040;margin-bottom:0.5rem;">
        <div style="display:flex;align-items:center;gap:0.6rem;">
            <div style="width:32px;height:32px;background:linear-gradient(135deg,#1a4fff,#00d4ff);
                        border-radius:8px;display:flex;align-items:center;justify-content:center;
                        font-size:1rem;">⚡</div>
            <div>
                <div style="font-size:1rem;font-weight:800;color:#ffffff;letter-spacing:-0.02em;">
                    Field AI Agent
                </div>
                <div style="color:#2a3a55;font-size:0.62rem;letter-spacing:0.1em;text-transform:uppercase;">
                    Powered by Azure
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    show_trace = st.toggle("Show Agent Reasoning Trace", value=False)

    st.markdown("### System Status")
    try:
        health = requests.get(f"{BACKEND_URL}/health", timeout=5)
        if health.status_code == 200:
            data = health.json()
            overall = data.get("status", "unknown")
            color = "#2ecc71" if overall == "healthy" else "#e74c3c"
            st.markdown(f"""
            <div style="background:#0a1628;border:1px solid #162040;border-radius:10px;
                        padding:0.8rem 1rem;margin-bottom:0.5rem;">
                <div style="color:{color};font-size:0.68rem;font-weight:800;
                            letter-spacing:0.12em;text-transform:uppercase;margin-bottom:0.6rem;">
                    ● {overall.upper()}
                </div>
            """, unsafe_allow_html=True)
            for svc, svc_status in data.get("services", {}).items():
                dot = "sdot-ok" if svc_status == "healthy" else "sdot-err"
                label = svc.replace("_", " ").title()
                st.markdown(f"""
                <div class="status-row">
                    <span class="sdot {dot}"></span>{label}
                </div>""", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
    except Exception:
        st.markdown(
            '<div style="color:#e74c3c;font-size:0.76rem;">● Backend unreachable</div>',
            unsafe_allow_html=True
        )

    st.markdown("### Knowledge Base")
    st.markdown("""
    <div style="background:#0a1628;border:1px solid #162040;border-radius:10px;padding:0.8rem 1rem;">
        <div style="color:#3a5070;font-size:0.76rem;line-height:2.2;">
            📋 ABB Production Handbook<br>
            📋 IOGP Life Saving Rules<br>
            📋 OSHA H2S Standards
        </div>
        <div style="border-top:1px solid #0f1e35;margin-top:0.6rem;padding-top:0.6rem;
                    color:#1e2d45;font-size:0.68rem;display:flex;justify-content:space-between;">
            <span>568 chunks indexed</span>
            <span style="color:#3d8ef0;">Hybrid search</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### Try These")
    examples = [
        "What is the H2S exposure limit for workers?",
        "How does a two-phase separator work?",
        "IOGP Life Saving Rules for working at height?",
        "Compare confined space vs working at height safety",
        "What PPE is required for H2S environments?",
    ]
    for q in examples:
        if st.button(q, use_container_width=True, key=f"ex_{q}"):
            st.session_state.run_query = q

# Hero
st.markdown("""
<div class="hero">
    <div class="hero-icon">⚡</div>
    <div class="hero-eyebrow">Enterprise AI</div>
    <h1 class="hero-title">
        Field <span class="accent">AI</span> <span class="accent2">Agent</span>
    </h1>
    <p class="hero-sub">Intelligent Technical Assistant · Oil &amp; Gas Operations</p>
    <div class="hero-tags">
        <span class="hero-tag">Azure OpenAI GPT-4o</span>
        <span class="hero-tag">LangGraph ReAct</span>
        <span class="hero-tag cyan">Hybrid RAG</span>
        <span class="hero-tag cyan">568 Chunks</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Query counter
if st.session_state.query_count > 0:
    st.markdown(f"""
    <div class="query-counter">
        <div class="query-counter-dot"></div>
        {st.session_state.query_count} question{"s" if st.session_state.query_count != 1 else ""} answered this session
    </div>
    """, unsafe_allow_html=True)

# Input
query = st.text_area(
    "ASK A TECHNICAL QUESTION",
    height=100,
    placeholder="e.g. What are the H2S exposure limits for confined space entry in oil and gas operations?"
)

col1, col2, col3 = st.columns([1.5, 1, 4])
with col1:
    submit = st.button("⚡ Ask Field AI Agent", type="primary", use_container_width=True)
with col2:
    if st.button("✕ Clear", use_container_width=True):
        st.session_state.run_query = ""
        st.session_state.last_result = None
        st.rerun()

# Determine active query
active_query = ""
if submit and query.strip():
    active_query = query.strip()
elif st.session_state.run_query:
    active_query = st.session_state.run_query
    st.session_state.run_query = ""

# Run query
if active_query:
    st.session_state.query_count += 1

    typing_placeholder = st.empty()
    typing_placeholder.markdown("""
    <div class="typing-indicator">
        <div class="typing-dots">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
        Searching through 568 oil &amp; gas document chunks...
    </div>
    """, unsafe_allow_html=True)

    try:
        response = requests.post(
            f"{BACKEND_URL}/query",
            json={"query": active_query, "include_trace": show_trace},
            timeout=120
        )
        typing_placeholder.empty()

        if response.status_code == 200:
            data = response.json()
            st.session_state.last_result = data

            q_type = data.get("query_type", "unknown")
            latency = data.get("latency_seconds", 0)
            chunks = data.get("chunks_retrieved", 0)
            sources = data.get("sources", [])
            badge_class = "badge-simple" if q_type == "simple" else "badge-complex"

            st.markdown(f"""
            <div class="metric-row">
                <div class="metric-card">
                    <span class="metric-icon">🎯</span>
                    <div class="metric-label">Query Type</div>
                    <div style="margin-top:0.3rem;">
                        <span class="badge {badge_class}">{q_type}</span>
                    </div>
                </div>
                <div class="metric-card">
                    <span class="metric-icon">⚡</span>
                    <div class="metric-label">Response Time</div>
                    <div class="metric-value">{latency}</div>
                    <div class="metric-unit">seconds</div>
                </div>
                <div class="metric-card">
                    <span class="metric-icon">📄</span>
                    <div class="metric-label">Chunks Retrieved</div>
                    <div class="metric-value">{chunks}</div>
                    <div class="metric-unit">document chunks</div>
                </div>
                <div class="metric-card">
                    <span class="metric-icon">📚</span>
                    <div class="metric-label">Sources Used</div>
                    <div class="metric-value">{len(sources)}</div>
                    <div class="metric-unit">unique pages</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown('<div class="sec-header">Answer</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="answer-box">{data["answer"]}</div>',
                unsafe_allow_html=True
            )

            if sources:
                st.markdown('<div class="sec-header">Sources</div>', unsafe_allow_html=True)
                chips = ""
                for s in sources:
                    parts = s.split(", Page ")
                    doc = parts[0].replace("_", " ").replace(".pdf", "")
                    page = parts[1] if len(parts) > 1 else "—"
                    chips += f"""
                    <span class="source-chip">
                        📋 <span class="source-doc">{doc}</span>
                        <span class="source-page">p.{page}</span>
                    </span>"""
                st.markdown(f'<div class="sources-wrap">{chips}</div>', unsafe_allow_html=True)

            if show_trace and data.get("reasoning_trace"):
                st.markdown('<div class="sec-header">Agent Reasoning</div>', unsafe_allow_html=True)
                with st.expander("View full reasoning trace", expanded=True):
                    for step in data["reasoning_trace"]:
                        st.markdown(f"""
                        <div class="trace-step">
                            <div class="trace-dot"></div>
                            <div>{step}</div>
                        </div>""", unsafe_allow_html=True)

        else:
            st.error(f"API Error {response.status_code}")

    except requests.exceptions.Timeout:
        typing_placeholder.empty()
        st.error("Request timed out. Complex queries can take up to 2 minutes.")
    except requests.exceptions.ConnectionError:
        typing_placeholder.empty()
        st.error("Cannot connect to Field AI Agent backend.")
    except Exception as e:
        typing_placeholder.empty()
        st.error(f"Unexpected error: {str(e)}")

elif submit and not query.strip():
    st.warning("Please enter a question before submitting.")

elif not active_query and st.session_state.last_result is None:
    st.markdown("""
    <div class="empty-state">
        <div class="empty-icon">⚡</div>
        <div class="empty-title">Ready to assist field engineers</div>
        <div class="empty-sub">
            Ask any technical question about oil &amp; gas operations,<br>
            equipment specifications, safety procedures, or regulatory standards.
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
<div class="footer">
    Field AI Agent v1.0 &nbsp;·&nbsp; Enterprise AI
    &nbsp;·&nbsp; Azure OpenAI + LangGraph + Azure AI Search
</div>
""", unsafe_allow_html=True)