# =============================================================================
# simple_rag.py — Basic RAG pipeline for OilMind
#
# Flow:
# User Question → Azure AI Search (hybrid retrieval) → Top 5 chunks
# → GPT-4o (answer generation with citations) → Answer + Sources
#
# This is the foundation retrieval layer.
# The LangGraph router (router.py) calls this for straightforward queries.
# Complex multi-step queries go to reflection_agent.py instead.
# =============================================================================

import os
import sys
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from backend.config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_EMBEDDING_DEPLOYMENT,
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_KEY,
    AZURE_SEARCH_INDEX,
    TOP_K_RESULTS
)


# =============================================================================
# SYSTEM PROMPT — Instructions GPT-4o follows for every answer
# =============================================================================

SYSTEM_PROMPT = """You are OilMind, an expert AI assistant for oil and gas 
operations at ChampionX. You answer questions from field engineers and 
operations teams based strictly on the provided technical documents.

Your rules:
1. Answer ONLY based on the provided document chunks below
2. ALWAYS cite your source — include the document name and page number
3. If the answer is not in the provided chunks, say clearly:
   "I could not find this information in the available documents."
4. Be precise and technically accurate — field engineers may act on your answers
5. For safety-critical procedures, always recommend verification with 
   the original document

Format your answer as:
- Direct answer first
- Supporting details
- Source: [document name, Page X]
"""


# =============================================================================
# CLIENT INITIALISATION
# =============================================================================

def get_clients():
    """
    Creates and returns Azure OpenAI and Azure AI Search clients.
    
    Why a separate function rather than global clients?
    Global clients initialised at import time can cause issues in testing
    and when environment variables aren't yet loaded.
    Initialising inside a function ensures config is fully loaded first.
    """
    
    openai_client = AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_KEY,
        api_version=AZURE_OPENAI_API_VERSION
    )
    
    search_client = SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_INDEX,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY)
    )
    
    return openai_client, search_client


# =============================================================================
# STEP 1: RETRIEVE — Hybrid search against Azure AI Search
# =============================================================================

def retrieve_chunks(
    query: str,
    search_client: SearchClient,
    openai_client: AzureOpenAI
) -> list[dict]:
    """
    Performs hybrid search — keyword + vector simultaneously.
    
    Why hybrid and not just vector?
    Oil and gas queries have two distinct patterns:
    
    Pattern 1 — Exact terminology: "API 510 inspection interval"
    A field engineer searching for a specific standard code needs
    exact keyword matching. Vector search alone might return
    semantically similar content that doesn't mention API 510 specifically.
    
    Pattern 2 — Conceptual queries: "what should I check before opening a valve"
    The document says "pre-operation isolation verification procedure"
    Vector search bridges this vocabulary gap. Keyword search alone would miss it.
    
    Hybrid search handles both patterns in a single query — it runs
    keyword BM25 scoring and vector cosine similarity simultaneously,
    then combines the scores using Reciprocal Rank Fusion (RRF).
    RRF doesn't just average the scores — it combines the rank positions
    from both searches, giving robust results even when one method
    scores a chunk much higher than the other.
    
    Args:
        query: The field engineer's question
        search_client: Azure AI Search client
        openai_client: Azure OpenAI client (for embedding the query)
        
    Returns:
        List of top K chunks with text and metadata
    """
    
    # Step 1a: Embed the query using the same model used at index time
    # This is critical — query and chunks must be in the same vector space
    query_embedding = openai_client.embeddings.create(
        model=AZURE_EMBEDDING_DEPLOYMENT,
        input=query
    ).data[0].embedding
    
    # Step 1b: Build the vector query component
    vector_query = VectorizedQuery(
        vector=query_embedding,
        k_nearest_neighbors=TOP_K_RESULTS,
        fields="text_vector"
        # tells Azure AI Search which field contains the vectors
    )
    
    # Step 1c: Execute hybrid search
    # search_text activates keyword BM25 search
    # vector_queries activates vector similarity search
    # Both run simultaneously, results merged via RRF
    results = search_client.search(
        search_text=query,          # keyword search component
        vector_queries=[vector_query],  # vector search component
        select=["chunk_id", "text", "source", "page_number"],
        top=TOP_K_RESULTS
    )
    
    # Collect results into a clean list
    chunks = []
    for result in results:
        chunks.append({
            "chunk_id": result["chunk_id"],
            "text": result["text"],
            "source": result["source"],
            "page_number": result["page_number"]
        })
    
    return chunks


# =============================================================================
# STEP 2: AUGMENT — Build the prompt with retrieved context
# =============================================================================

def build_prompt(query: str, chunks: list[dict]) -> str:
    """
    Builds the user prompt by combining the question with retrieved chunks.
    
    Why structure it this way?
    GPT-4o needs to know clearly:
    1. What documents it has access to
    2. Where each piece of content came from
    3. What the actual question is
    
    Structuring the context with clear source labels means GPT-4o
    can generate citations that reference specific documents and pages —
    not just summarise content without attribution.
    
    This is called prompt augmentation — the A in RAG.
    """
    
    # Build context block from retrieved chunks
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[Source {i}: {chunk['source']}, Page {chunk['page_number']}]\n"
            f"{chunk['text']}"
        )
    
    context = "\n\n---\n\n".join(context_parts)
    
    # Final prompt structure
    prompt = f"""Based on the following oil and gas technical documents, 
answer the question below. Always cite the source document and page number.

DOCUMENTS:
{context}

QUESTION: {query}

ANSWER:"""
    
    return prompt


# =============================================================================
# STEP 3: GENERATE — GPT-4o produces the cited answer
# =============================================================================

def generate_answer(
    prompt: str,
    openai_client: AzureOpenAI
) -> str:
    """
    Sends the augmented prompt to GPT-4o and returns the answer.
    
    Temperature=0 is a deliberate choice for a safety-critical system.
    
    Temperature controls randomness in GPT-4o's output:
    - Temperature 1.0 = creative, varied, sometimes unpredictable
    - Temperature 0.0 = deterministic, consistent, factual
    
    For a field engineer asking about H2S exposure limits or
    isolation procedures, we want the same correct answer every time —
    not creative variation. Temperature 0 enforces factual consistency.
    
    max_tokens=1000 caps the response length.
    Oil and gas answers should be precise and actionable, not essays.
    """
    
    response = openai_client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0,      # deterministic — same question, same answer
        max_tokens=1000     # precise and actionable, not verbose
    )
    
    return response.choices[0].message.content


# =============================================================================
# MASTER FUNCTION — Orchestrates the full RAG pipeline
# =============================================================================

def simple_rag_query(query: str) -> dict:
    """
    Complete RAG pipeline in one function call.
    
    This is the function called by:
    - The LangGraph router for simple queries
    - The FastAPI endpoint directly for API calls
    - The test below for verification
    
    Args:
        query: The field engineer's question in natural language
        
    Returns:
        Dict containing:
        - answer: GPT-4o's cited answer
        - sources: List of source documents and pages used
        - chunks_retrieved: Number of chunks retrieved
    """
    
    openai_client, search_client = get_clients()
    
    # Step 1: Retrieve relevant chunks
    chunks = retrieve_chunks(query, search_client, openai_client)
    
    if not chunks:
        return {
            "answer": "I could not find relevant information in the available documents.",
            "sources": [],
            "chunks_retrieved": 0
        }
    
    # Step 2: Build augmented prompt
    prompt = build_prompt(query, chunks)
    
    # Step 3: Generate cited answer
    answer = generate_answer(prompt, openai_client)
    
    # Extract unique sources for the response metadata
    sources = list({
        f"{chunk['source']}, Page {chunk['page_number']}"
        for chunk in chunks
    })
    
    return {
        "answer": answer,
        "sources": sources,
        "chunks_retrieved": len(chunks)
    }


# =============================================================================
# TEST — Run this file directly to ask OilMind its first question
# =============================================================================

if __name__ == "__main__":
    
    print("=" * 60)
    print("OilMind — Simple RAG Test")
    print("=" * 60)
    
    # Test with three real oil & gas questions
    test_questions = [
        "What are the H2S exposure limits for workers in oil and gas operations?",        "What are the IOGP Life Saving Rules for working at height?",
        "How does a two-phase separator work in oil production?"
    ]
    
    for question in test_questions:
        print(f"\n🔍 QUESTION: {question}")
        print("-" * 60)
        
        result = simple_rag_query(question)
        
        print(f"💬 ANSWER:\n{result['answer']}")
        print(f"\n📚 SOURCES USED:")
        for source in result['sources']:
            print(f"   - {source}")
        print(f"\n📊 Chunks retrieved: {result['chunks_retrieved']}")
        print("=" * 60)
