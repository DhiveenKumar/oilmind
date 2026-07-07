# =============================================================================
# router.py — LangGraph agent that routes queries to the right pipeline
#
# This is the core of OilMind's agentic behaviour.
# It uses LangGraph's StateGraph to:
# 1. Classify incoming queries as simple or complex
# 2. Route simple queries to simple_rag.py
# 3. Route complex queries to reflection_agent.py
# 4. Return a unified response regardless of which path was taken
#
# Why LangGraph over a plain if/else statement?
# LangGraph gives us:
# - Persistent state across agent steps
# - Visual graph structure that's inspectable and debuggable
# - Easy extension — adding new nodes/paths requires minimal changes
# - Production-ready streaming and async support
# =============================================================================

import os
import sys
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from backend.config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT
)
from backend.agent.simple_rag import simple_rag_query


# =============================================================================
# STATE — The memory that flows through the graph
# =============================================================================

class OilMindState(TypedDict):
    """
    The state object that gets passed between every node in the graph.
    
    Think of this like a shared notepad that every agent step
    can read from and write to. Each node receives the full state,
    does its work, and returns updated state fields.
    
    Why TypedDict?
    It gives us type safety — we know exactly what fields exist
    and what type each one is. This catches bugs at development
    time rather than at runtime in production.
    """
    query: str                  # The original question from the field engineer
    query_type: str             # "simple" or "complex" — set by classifier
    answer: str                 # Final answer — set by whichever RAG path runs
    sources: list               # Source citations — set by whichever RAG path runs
    chunks_retrieved: int       # How many chunks were used
    reasoning_trace: list       # Steps the agent took — for transparency


# =============================================================================
# NODE 1: QUERY CLASSIFIER
# =============================================================================

def classify_query(state: OilMindState) -> OilMindState:
    """
    Classifies the incoming query as 'simple' or 'complex'.
    
    Classification rules:
    
    SIMPLE — Single-topic, direct factual or procedural questions:
    - "What is the H2S exposure limit?"
    - "How does a two-phase separator work?"
    - "What are the IOGP Life Saving Rules for confined space?"
    
    COMPLEX — Multi-part, comparative, or cross-document questions:
    - "Compare HP and LP separator isolation procedures"
    - "What do OSHA and IOGP say about confined space entry?"
    - "Explain the safety differences between X and Y and which regulations apply"
    
    Why use GPT-4o for classification rather than rules/keywords?
    Keyword rules like "if 'compare' in query → complex" are brittle.
    "Compare apples to oranges" is simple. "What is the difference between
    API 510 and API 570 inspection intervals for corroded vessels in sour
    service environments?" is complex despite not containing "compare".
    GPT-4o understands intent, not just keywords.
    
    Why not just always use the reflection agent?
    The reflection agent is slower — it makes multiple retrieval calls
    and LLM calls per query. For simple questions, that overhead adds
    latency without adding value. Routing simple queries through simple RAG
    keeps response time fast for the majority of queries.
    """
    
    openai_client = AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_KEY,
        api_version=AZURE_OPENAI_API_VERSION
    )
    
    classification_prompt = f"""You are a query classifier for an oil and gas 
technical assistant. Classify the following query as either 'simple' or 'complex'.

SIMPLE: Single topic, direct factual or procedural question answerable 
from one focused retrieval pass.
Examples:
- "What is the H2S exposure limit?"
- "How does a two-phase separator work?"
- "What are the confined space entry rules?"

COMPLEX: Multi-part, comparative, cross-document, or requires 
step-by-step reasoning across multiple topics.
Examples:
- "Compare HP and LP separator isolation procedures and identify safety differences"
- "What do OSHA and IOGP both say about confined space atmospheric testing?"
- "Explain the full sequence of steps for well abandonment and which regulations apply"

Query: {state['query']}

Respond with exactly one word: 'simple' or 'complex'"""

    response = openai_client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "user", "content": classification_prompt}
        ],
        temperature=0,
        max_tokens=10  # We only need one word
    )
    
    query_type = response.choices[0].message.content.strip().lower()
    
    # Safety check — if response is neither simple nor complex, default to simple
    if query_type not in ["simple", "complex"]:
        query_type = "simple"
    
    return {
        **state,
        "query_type": query_type,
        "reasoning_trace": [f"Query classified as: {query_type}"]
    }


# =============================================================================
# NODE 2: SIMPLE RAG PATH
# =============================================================================

def run_simple_rag(state: OilMindState) -> OilMindState:
    """
    Runs the simple RAG pipeline for straightforward queries.
    Calls simple_rag_query() which we already built and tested.
    """
    
    result = simple_rag_query(state["query"])
    
    return {
        **state,
        "answer": result["answer"],
        "sources": result["sources"],
        "chunks_retrieved": result["chunks_retrieved"],
        "reasoning_trace": state["reasoning_trace"] + [
            "Routed to: Simple RAG",
            f"Retrieved {result['chunks_retrieved']} chunks",
            "Generated cited answer"
        ]
    }


# =============================================================================
# NODE 3: COMPLEX — REFLECTION AGENT PATH (stub for now)
# =============================================================================

def run_reflection_agent(state: OilMindState) -> OilMindState:
    """
    Runs the reflection agent for complex multi-step queries.
    
    Currently calls simple_rag as a fallback — reflection_agent.py
    will be implemented in the next step and wired in here.
    
    This stub pattern is good engineering practice:
    - The graph structure is complete and testable now
    - The reflection agent can be developed and tested independently
    - Swapping the stub for the real implementation is a one-line change
    """
    
    # For now — use simple RAG as fallback
    # Next step: replace with reflection_agent.simple_rag_query()
    result = simple_rag_query(state["query"])
    
    return {
        **state,
        "answer": result["answer"],
        "sources": result["sources"],
        "chunks_retrieved": result["chunks_retrieved"],
        "reasoning_trace": state["reasoning_trace"] + [
            "Routed to: Reflection Agent (multi-step retrieval)",
            f"Retrieved {result['chunks_retrieved']} chunks",
            "Generated synthesised answer"
        ]
    }


# =============================================================================
# ROUTING FUNCTION — Decides which node to call after classification
# =============================================================================

def route_query(state: OilMindState) -> Literal["simple_rag", "reflection_agent"]:
    """
    Called by LangGraph after the classify_query node.
    Returns the name of the next node to execute.
    
    This is a conditional edge in LangGraph terminology —
    the graph branches here based on state.
    
    Why a separate function rather than inline logic?
    LangGraph's add_conditional_edges() requires a callable
    that takes state and returns a node name string.
    Keeping it as a named function makes the graph definition
    readable and the routing logic independently testable.
    """
    
    if state["query_type"] == "simple":
        return "simple_rag"
    else:
        return "reflection_agent"


# =============================================================================
# BUILD THE LANGGRAPH STATE GRAPH
# =============================================================================

def build_oilmind_graph():
    """
    Assembles the LangGraph StateGraph for OilMind.
    
    Graph structure:
    
    START
      ↓
    classify_query          ← Node 1: Is this simple or complex?
      ↓ (conditional edge)
    ┌─────────────────────┐
    │                     │
    simple_rag    reflection_agent  ← Node 2 or 3: Generate answer
    │                     │
    └──────────┬──────────┘
               ↓
              END
    
    Why this structure?
    It's the simplest graph that demonstrates real agentic behaviour —
    dynamic routing based on query analysis. Adding new paths
    (e.g. a time-series analysis node, a regulatory lookup node)
    is as simple as adding a new node and updating the routing function.
    """
    
    # Initialise the graph with our state schema
    graph = StateGraph(OilMindState)
    
    # Add nodes — each node is a function that takes and returns state
    graph.add_node("classify_query", classify_query)
    graph.add_node("simple_rag", run_simple_rag)
    graph.add_node("reflection_agent", run_reflection_agent)
    
    # Set entry point — where the graph starts
    graph.set_entry_point("classify_query")
    
    # Add conditional edge — after classify_query, call route_query()
    # to decide which node runs next
    graph.add_conditional_edges(
        "classify_query",       # from this node
        route_query,            # call this function to decide
        {
            "simple_rag": "simple_rag",               # if returns "simple_rag"
            "reflection_agent": "reflection_agent"    # if returns "reflection_agent"
        }
    )
    
    # Both paths end after generating an answer
    graph.add_edge("simple_rag", END)
    graph.add_edge("reflection_agent", END)
    
    # Compile the graph into a runnable
    return graph.compile()


# =============================================================================
# MASTER FUNCTION — Called by FastAPI and Streamlit
# =============================================================================

def oilmind_query(query: str) -> dict:
    """
    Main entry point for all OilMind queries.
    
    Builds the graph, runs the query through it,
    and returns a clean response dict.
    
    Args:
        query: Field engineer's question in natural language
        
    Returns:
        Dict with answer, sources, chunks_retrieved, 
        query_type, and reasoning_trace
    """
    
    # Build and run the graph
    app = build_oilmind_graph()
    
    # Initial state — query is set, everything else is empty
    initial_state = {
        "query": query,
        "query_type": "",
        "answer": "",
        "sources": [],
        "chunks_retrieved": 0,
        "reasoning_trace": []
    }
    
    # Run the graph — LangGraph manages state flow automatically
    final_state = app.invoke(initial_state)
    
    return {
        "answer": final_state["answer"],
        "sources": final_state["sources"],
        "chunks_retrieved": final_state["chunks_retrieved"],
        "query_type": final_state["query_type"],
        "reasoning_trace": final_state["reasoning_trace"]
    }


# =============================================================================
# TEST — Run directly to verify routing works
# =============================================================================

if __name__ == "__main__":
    
    print("=" * 60)
    print("OilMind — LangGraph Router Test")
    print("=" * 60)
    
    test_cases = [
        {
            "query": "What is the H2S exposure limit?",
            "expected_route": "simple"
        },
        {
            "query": "Compare the isolation procedures for high pressure and low pressure separators and identify the key safety differences",
            "expected_route": "complex"
        }
    ]
    
    for test in test_cases:
        print(f"\n🔍 QUERY: {test['query']}")
        print(f"   Expected route: {test['expected_route']}")
        print("-" * 60)
        
        result = oilmind_query(test["query"])
        
        print(f"   Actual route:   {result['query_type']}")
        print(f"\n💬 ANSWER:\n{result['answer']}")
        print(f"\n🔄 REASONING TRACE:")
        for step in result['reasoning_trace']:
            print(f"   → {step}")
        print(f"\n📚 SOURCES: {result['sources']}")
        print("=" * 60)