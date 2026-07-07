import streamlit as st
import requests
import os

st.set_page_config(
    page_title="OilMind — ChampionX Technical Assistant",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded"
)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        text-align: center;
        color: white;
    }
    .answer-box {
        background-color: #f8f9fa;
        border-left: 4px solid #0f3460;
        padding: 1.5rem;
        border-radius: 0 8px 8px 0;
        margin: 1rem 0;
        color: #1a1a2e;
    }
    .source-badge {
        background-color: #e8f0fe;
        color: #1a73e8;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 0.85rem;
        margin: 0.2rem;
        display: inline-block;
    }
    .badge-simple {
        background-color: #d4edda;
        color: #155724;
        padding: 0.2rem 0.6rem;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .badge-complex {
        background-color: #fff3cd;
        color: #856404;
        padding: 0.2rem 0.6rem;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
    <h1>🛢️ OilMind</h1>
    <p style="font-size: 1.1rem; margin: 0; opacity: 0.9;">
        Intelligent Technical Assistant for Oil & Gas Operations
    </p>
    <p style="font-size: 0.85rem; margin-top: 0.5rem; opacity: 0.7;">
        ChampionX | Powered by Azure OpenAI + Azure AI Search
    </p>
</div>
""", unsafe_allow_html=True)

# Initialize session state
if "query_input" not in st.session_state:
    st.session_state.query_input = ""
if "submitted_query" not in st.session_state:
    st.session_state.submitted_query = ""

with st.sidebar:
    st.image("https://via.placeholder.com/150x50/0f3460/ffffff?text=ChampionX",
             use_container_width=True)

    st.markdown("### About OilMind")
    st.markdown("""
    OilMind allows field engineers and operations teams to query 
    technical documentation using natural language.
    
    **Knowledge Base:**
    - ABB Oil & Gas Production Handbook
    - IOGP Life Saving Rules
    - OSHA H2S Safety Standards
    
    **Capabilities:**
    - Equipment specifications
    - Safety procedures
    - Regulatory standards
    - Operational guidelines
    """)

    st.markdown("---")
    show_trace = st.toggle("Show Agent Reasoning Trace", value=False)
    st.markdown("---")

    st.markdown("### Example Questions")

    example_questions = [
        "What is the H2S exposure limit for workers?",
        "How does a two-phase separator work?",
        "What are the IOGP Life Saving Rules for working at height?",
        "Compare confined space and working at height safety procedures",
        "What PPE is required for H2S environments?"
    ]

    for question in example_questions:
        if st.button(question, use_container_width=True, key=f"btn_{question}"):
            st.session_state.query_input = question
            st.session_state.submitted_query = question
            st.rerun()

    st.markdown("---")
    st.markdown("### System Status")
    try:
        health = requests.get(f"{BACKEND_URL}/health", timeout=5)
        if health.status_code == 200:
            data = health.json()
            status = data.get("status", "unknown")
            if status == "healthy":
                st.success("✅ All systems operational")
            else:
                st.warning("⚠️ Some services degraded")
            services = data.get("services", {})
            for service, svc_status in services.items():
                icon = "✅" if svc_status == "healthy" else "❌"
                st.caption(f"{icon} {service.replace('_', ' ').title()}")
        else:
            st.error("❌ Backend unreachable")
    except Exception:
        st.error("❌ Backend unreachable")

# Main query area
query = st.text_area(
    "Ask a technical question about oil & gas operations:",
    height=100,
    value=st.session_state.query_input,
    placeholder="e.g. What are the H2S exposure limits for confined space entry?"
)

# Update session state when user types
st.session_state.query_input = query

col1, col2, col3 = st.columns([1, 1, 4])

with col1:
    submit = st.button("🔍 Ask OilMind", type="primary", use_container_width=True)

with col2:
    clear = st.button("🗑️ Clear", use_container_width=True)
    if clear:
        st.session_state.query_input = ""
        st.session_state.submitted_query = ""
        st.rerun()

# Use either manual submit or auto-submit from example question
active_query = ""
if submit and query.strip():
    active_query = query
elif st.session_state.submitted_query:
    active_query = st.session_state.submitted_query
    st.session_state.submitted_query = ""

if active_query:
    with st.spinner("OilMind is searching through technical documentation..."):
        try:
            response = requests.post(
                f"{BACKEND_URL}/query",
                json={"query": active_query, "include_trace": show_trace},
                timeout=120
            )

            if response.status_code == 200:
                data = response.json()

                st.markdown("---")
                m1, m2, m3, m4 = st.columns(4)

                with m1:
                    query_type = data.get("query_type", "unknown")
                    badge_class = "badge-simple" if query_type == "simple" else "badge-complex"
                    st.markdown(
                        f"**Query Type**<br><span class='{badge_class}'>{query_type.upper()}</span>",
                        unsafe_allow_html=True
                    )
                with m2:
                    st.metric("Response Time", f"{data.get('latency_seconds', 0)}s")
                with m3:
                    st.metric("Chunks Retrieved", data.get("chunks_retrieved", 0))
                with m4:
                    st.metric("Sources Used", len(data.get("sources", [])))

                st.markdown("### 💬 Answer")
                st.markdown(
                    f"<div class='answer-box'>{data['answer']}</div>",
                    unsafe_allow_html=True
                )

                st.markdown("### 📚 Sources")
                sources = data.get("sources", [])
                if sources:
                    source_html = "".join(
                        f"<span class='source-badge'>📄 {source}</span>"
                        for source in sources
                    )
                    st.markdown(source_html, unsafe_allow_html=True)
                else:
                    st.caption("No sources retrieved")

                if show_trace and data.get("reasoning_trace"):
                    with st.expander("🔄 Agent Reasoning Trace", expanded=False):
                        for step in data["reasoning_trace"]:
                            st.markdown(f"→ {step}")

            else:
                st.error(f"API Error {response.status_code}")

        except requests.exceptions.Timeout:
            st.error("Request timed out. Complex queries can take up to 2 minutes.")
        except requests.exceptions.ConnectionError:
            st.error("Cannot connect to OilMind backend. Make sure the FastAPI server is running.")
        except Exception as e:
            st.error(f"Unexpected error: {str(e)}")

elif submit and not query.strip():
    st.warning("Please enter a question before clicking Ask OilMind.")

st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: #666; font-size: 0.8rem;'>"
    "OilMind v1.0 | ChampionX Internal Tool | "
    "Powered by Azure OpenAI + LangGraph + Azure AI Search"
    "</p>",
    unsafe_allow_html=True
)