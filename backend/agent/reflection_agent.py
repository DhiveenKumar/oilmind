# =============================================================================
# reflection_agent.py — ReAct loop for complex multi-step O&G queries
#
# ReAct = Reason + Act
# The agent reasons about what information it needs,
# acts by retrieving it, reflects on whether it's sufficient,
# and repeats until it can give a complete answer.
#
# Max iterations: 3
# Why 3? Enough for most complex queries. Beyond 3 iterations,
# the query is likely outside the corpus scope entirely.
# Capping prevents infinite loops — critical in production.
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
# SYSTEM PROMPT FOR REFLECTION AGENT
# =============================================================================

REFLECTION_SYSTEM_PROMPT = """You are OilMind, an expert AI assistant for 
oil and gas operations at ChampionX. You handle complex, multi-part technical 
questions by reasoning step by step.

Your approach:
1. Break complex questions into focused sub-questions
2. Search for each sub-question separately  
3. Reflect on whether you have sufficient information
4. Synthesise findings into a complete, cited answer

Always cite sources with document name and page number.
Never fabricate information not found in the retrieved documents.
For safety-critical information, recommend verification with original documents.
"""


# =============================================================================
# CLIENT SETUP
# =============================================================================

def get_clients():
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
# RETRIEVAL — Same hybrid search as simple_rag.py
# =============================================================================

def retrieve_chunks(
    query: str,
    search_client: SearchClient,
    openai_client: AzureOpenAI,
    top_k: int = TOP_K_RESULTS
) -> list[dict]:
    """
    Hybrid search — identical to simple_rag.py.
    Called multiple times per complex query — once per sub-question.
    """
    
    # Embed the sub-question
    query_embedding = openai_client.embeddings.create(
        model=AZURE_EMBEDDING_DEPLOYMENT,
        input=query
    ).data[0].embedding
    
    vector_query = VectorizedQuery(
        vector=query_embedding,
        k_nearest_neighbors=top_k,
        fields="text_vector"
    )
    
    results = search_client.search(
        search_text=query,
        vector_queries=[vector_query],
        select=["chunk_id", "text", "source", "page_number"],
        top=top_k
    )
    
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
# STEP 1: DECOMPOSE — Break complex query into sub-questions
# =============================================================================

def decompose_query(
    query: str,
    openai_client: AzureOpenAI
) -> list[str]:
    """
    Uses GPT-4o to break a complex query into focused sub-questions.
    
    Why decompose?
    A complex query like "compare HP and LP separator isolation procedures
    and identify applicable OSHA regulations" contains three information needs:
    1. HP separator isolation procedure
    2. LP separator isolation procedure  
    3. Applicable OSHA regulations
    
    Searching for the full complex query returns chunks that partially
    match the overall topic but may miss specific sub-topics entirely.
    Searching for each sub-question separately gets precise, focused
    chunks for each information need.
    
    This is called query decomposition — a standard technique for
    improving RAG performance on multi-part questions.
    """
    
    decompose_prompt = f"""You are helping an oil and gas technical assistant 
break down a complex question into focused sub-questions for document retrieval.

Complex question: {query}

Break this into 2-4 specific, focused sub-questions that together 
cover all aspects of the original question. Each sub-question should 
be searchable independently.

Return ONLY the sub-questions, one per line, no numbering, no explanations."""

    response = openai_client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "user", "content": decompose_prompt}
        ],
        temperature=0,
        max_tokens=200
    )
    
    # Split response into individual sub-questions
    sub_questions = [
        q.strip() 
        for q in response.choices[0].message.content.strip().split('\n')
        if q.strip()  # Remove empty lines
    ]
    
    return sub_questions


# =============================================================================
# STEP 2: REFLECT — Check if retrieved information is sufficient
# =============================================================================

def reflect_on_sufficiency(
    original_query: str,
    sub_questions: list[str],
    all_chunks: list[dict],
    openai_client: AzureOpenAI
) -> dict:
    """
    Asks GPT-4o to evaluate whether the retrieved chunks are sufficient
    to answer the original complex question completely.
    
    This is the Reflection part of ReAct.
    
    Why reflect?
    Without reflection, the agent would always answer with whatever
    it retrieved — even if that's incomplete. Reflection gives the
    agent self-awareness about the quality of its information.
    
    If reflection finds gaps, the agent formulates new sub-questions
    to fill those gaps and retrieves again — up to MAX_ITERATIONS times.
    
    Returns:
        dict with:
        - sufficient: bool — is the information complete enough to answer?
        - gaps: list[str] — what specific information is still missing?
        - additional_queries: list[str] — what to search for next
    """
    
    # Build context summary for reflection
    context_summary = ""
    for i, chunk in enumerate(all_chunks[:10], 1):  # Show first 10 chunks
        context_summary += (
            f"[{i}] {chunk['source']}, Page {chunk['page_number']}:\n"
            f"{chunk['text'][:200]}...\n\n"
        )
    
    reflect_prompt = f"""You are evaluating whether retrieved document chunks 
provide sufficient information to fully answer a complex oil and gas question.

ORIGINAL QUESTION: {original_query}

SUB-QUESTIONS WE SEARCHED FOR:
{chr(10).join(f'- {q}' for q in sub_questions)}

RETRIEVED CHUNKS SUMMARY:
{context_summary}

Evaluate:
1. Is there sufficient information to answer ALL parts of the original question?
2. What specific information is still missing, if any?
3. What additional search queries would fill the gaps?

Respond in this exact format:
SUFFICIENT: yes/no
GAPS: [list missing information, or 'none' if sufficient]
ADDITIONAL_QUERIES: [list new search queries, or 'none' if sufficient]"""

    response = openai_client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "user", "content": reflect_prompt}
        ],
        temperature=0,
        max_tokens=300
    )
    
    reflection_text = response.choices[0].message.content.strip()
    
    # Parse reflection response
    sufficient = "SUFFICIENT: yes" in reflection_text.lower()
    
    # Extract additional queries if needed
    additional_queries = []
    if not sufficient and "ADDITIONAL_QUERIES:" in reflection_text:
        queries_section = reflection_text.split("ADDITIONAL_QUERIES:")[1].strip()
        if queries_section.lower() != "none":
            additional_queries = [
                q.strip().lstrip('- ').strip()
                for q in queries_section.split('\n')
                if q.strip() and q.strip().lower() != 'none'
            ]
    
    return {
        "sufficient": sufficient,
        "additional_queries": additional_queries[:2],  # Max 2 follow-up queries
        "reflection_text": reflection_text
    }


# =============================================================================
# STEP 3: SYNTHESISE — Generate final answer from all retrieved chunks
# =============================================================================

def synthesise_answer(
    original_query: str,
    all_chunks: list[dict],
    reasoning_steps: list[str],
    openai_client: AzureOpenAI
) -> str:
    """
    Generates the final comprehensive answer from all retrieved chunks.
    
    Unlike simple_rag.py which uses the top 5 chunks directly,
    the reflection agent accumulates chunks across multiple retrieval
    passes and synthesises across all of them.
    
    Deduplication: chunks are deduplicated by chunk_id before synthesis
    to avoid the model seeing the same content twice.
    """
    
    # Deduplicate chunks by chunk_id
    seen_ids = set()
    unique_chunks = []
    for chunk in all_chunks:
        if chunk["chunk_id"] not in seen_ids:
            seen_ids.add(chunk["chunk_id"])
            unique_chunks.append(chunk)
    
    # Build context from unique chunks
    context_parts = []
    for i, chunk in enumerate(unique_chunks, 1):
        context_parts.append(
            f"[Source {i}: {chunk['source']}, Page {chunk['page_number']}]\n"
            f"{chunk['text']}"
        )
    
    context = "\n\n---\n\n".join(context_parts)
    
    # Build reasoning summary for context
    reasoning_summary = "\n".join(f"- {step}" for step in reasoning_steps)
    
    synthesis_prompt = f"""You are OilMind, an expert oil and gas technical 
assistant. Using the retrieved documents below, provide a comprehensive answer 
to the following complex question.

The question was answered through multiple retrieval steps:
{reasoning_summary}

RETRIEVED DOCUMENTS:
{context}

COMPLEX QUESTION: {original_query}

Provide a complete, well-structured answer that:
1. Addresses ALL parts of the original question
2. Cites specific sources for each major point
3. Clearly distinguishes between different topics if the question is comparative
4. Flags any information that could not be found in the documents

COMPREHENSIVE ANSWER:"""

    response = openai_client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
            {"role": "user", "content": synthesis_prompt}
        ],
        temperature=0,
        max_tokens=1500  # Longer than simple RAG — complex answers need more space
    )
    
    return response.choices[0].message.content


# =============================================================================
# MASTER FUNCTION — Full ReAct loop
# =============================================================================

def reflection_agent_query(query: str) -> dict:
    """
    Runs the complete ReAct loop for complex queries.
    
    Loop structure:
    1. Decompose query into sub-questions
    2. Retrieve chunks for each sub-question
    3. Reflect — is information sufficient?
    4. If not sufficient and iterations remain → retrieve more
    5. Synthesise final answer from all collected chunks
    
    MAX_ITERATIONS = 3
    Each iteration adds retrieval calls and LLM calls.
    3 iterations is the right balance between thoroughness and latency.
    """
    
    MAX_ITERATIONS = 3
    
    openai_client, search_client = get_clients()
    
    all_chunks = []
    all_sub_questions = []
    reasoning_steps = []
    iteration = 0
    
    print(f"\n🤔 Reflection Agent activated for complex query")
    print(f"   Query: {query[:80]}...")
    
    # -------------------------------------------------------------------------
    # ITERATION LOOP
    # -------------------------------------------------------------------------
    
    while iteration < MAX_ITERATIONS:
        iteration += 1
        print(f"\n   Iteration {iteration}/{MAX_ITERATIONS}")
        
        # Step 1: Decompose (only on first iteration)
        # On subsequent iterations, use additional queries from reflection
        if iteration == 1:
            sub_questions = decompose_query(query, openai_client)
            print(f"   📋 Decomposed into {len(sub_questions)} sub-questions:")
            for sq in sub_questions:
                print(f"      - {sq}")
        
        all_sub_questions.extend(sub_questions)
        reasoning_steps.append(
            f"Iteration {iteration}: Searching for {len(sub_questions)} sub-questions"
        )
        
        # Step 2: Retrieve chunks for each sub-question
        iteration_chunks = []
        for sub_q in sub_questions:
            chunks = retrieve_chunks(sub_q, search_client, openai_client)
            iteration_chunks.extend(chunks)
            print(f"   🔍 '{sub_q[:50]}...' → {len(chunks)} chunks")
        
        all_chunks.extend(iteration_chunks)
        reasoning_steps.append(
            f"Iteration {iteration}: Retrieved {len(iteration_chunks)} chunks total"
        )
        
        # Step 3: Reflect — is information sufficient?
        reflection = reflect_on_sufficiency(
            query, all_sub_questions, all_chunks, openai_client
        )
        
        print(f"   💭 Reflection: {'✅ Sufficient' if reflection['sufficient'] else '❌ Need more information'}")
        
        if reflection["sufficient"]:
            reasoning_steps.append("Reflection: Information sufficient — proceeding to synthesis")
            break
        else:
            reasoning_steps.append(
                f"Reflection: Gaps identified — searching {len(reflection['additional_queries'])} more queries"
            )
            # Use additional queries for next iteration
            sub_questions = reflection["additional_queries"]
            
            if not sub_questions:
                # No additional queries suggested — exit loop
                break
    
    # -------------------------------------------------------------------------
    # SYNTHESISE FINAL ANSWER
    # -------------------------------------------------------------------------
    
    print(f"\n   📝 Synthesising answer from {len(all_chunks)} total chunks...")
    reasoning_steps.append(f"Synthesis: Combining {len(all_chunks)} chunks from {iteration} iteration(s)")
    
    answer = synthesise_answer(query, all_chunks, reasoning_steps, openai_client)
    
    # Extract unique sources
    seen_sources = set()
    sources = []
    for chunk in all_chunks:
        source_str = f"{chunk['source']}, Page {chunk['page_number']}"
        if source_str not in seen_sources:
            seen_sources.add(source_str)
            sources.append(source_str)
    
    print(f"   ✅ Answer synthesised from {len(sources)} unique sources")
    
    return {
        "answer": answer,
        "sources": sources,
        "chunks_retrieved": len(all_chunks),
        "iterations": iteration,
        "reasoning_steps": reasoning_steps
    }


# =============================================================================
# TEST — Run directly to verify reflection agent works
# =============================================================================

if __name__ == "__main__":
    
    print("=" * 60)
    print("OilMind — Reflection Agent Test")
    print("=" * 60)
    
    # Complex multi-part question — requires reflection
    complex_query = (
        "Compare the safety procedures for working in confined spaces "
        "versus working at height in oil and gas operations — "
        "what are the key differences in hazards, protective equipment, "
        "and permit requirements?"
    )
    
    print(f"\n🔍 COMPLEX QUERY:\n{complex_query}\n")
    print("-" * 60)
    
    result = reflection_agent_query(complex_query)
    
    print(f"\n💬 FINAL ANSWER:\n{result['answer']}")
    print(f"\n📊 STATS:")
    print(f"   Iterations:       {result['iterations']}")
    print(f"   Total chunks:     {result['chunks_retrieved']}")
    print(f"   Unique sources:   {len(result['sources'])}")
    print(f"\n📚 SOURCES USED:")
    for source in result['sources']:
        print(f"   - {source}")
    print(f"\n🔄 REASONING STEPS:")
    for step in result['reasoning_steps']:
        print(f"   → {step}")
    print("=" * 60)