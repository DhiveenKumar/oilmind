# =============================================================================
# run_ragas.py — RAGAS evaluation for OilMind
#
# Measures four quality dimensions:
# 1. Faithfulness      — are answers grounded in retrieved documents?
# 2. Answer Relevancy  — do answers address the actual question?
# 3. Context Precision — are retrieved chunks relevant?
# 4. Context Recall    — did we retrieve all needed information?
# =============================================================================

import os
import sys
import json
import time
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall
)
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

from backend.agent.simple_rag import simple_rag_query, retrieve_chunks, get_clients
from backend.config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_EMBEDDING_DEPLOYMENT
)


# =============================================================================
# LOAD TEST SET
# =============================================================================

def load_test_set(path: str) -> list[dict]:
    with open(path, 'r') as f:
        data = json.load(f)
    return data['test_cases']


# =============================================================================
# RUN QUERIES AND COLLECT RESULTS
# =============================================================================

def collect_rag_results(test_cases: list[dict]) -> list[dict]:
    """
    Runs each test question through OilMind and collects:
    - The generated answer
    - The retrieved contexts
    - The original question
    - The reference answer
    """

    print(f"\n🔄 Running {len(test_cases)} test questions through OilMind...")
    print("   This will take 3-5 minutes\n")

    results = []
    openai_client, search_client = get_clients()

    for i, case in enumerate(test_cases, 1):
        print(f"   [{i}/{len(test_cases)}] {case['question'][:60]}...")

        try:
            # Get RAG result
            result = simple_rag_query(case['question'])

            # Get the actual chunks for context
            chunks = retrieve_chunks(
                case['question'],
                search_client,
                openai_client
            )

            # Extract just the text from chunks
            contexts = [chunk['text'] for chunk in chunks]

            results.append({
                'question': case['question'],
                'answer': result['answer'],
                'contexts': contexts,
                'ground_truth': case['reference_answer'],
                'category': case['category']
            })

            # Rate limit protection
            time.sleep(1)

        except Exception as e:
            print(f"   ❌ Error on question {i}: {e}")
            continue

    print(f"\n✅ Collected results for {len(results)} questions")
    return results


# =============================================================================
# RUN RAGAS EVALUATION
# =============================================================================

def run_ragas_evaluation(results: list[dict]) -> tuple:
    """
    Passes collected results to RAGAS for metric computation.
    Returns both the scores object and the pandas dataframe.
    """

    print("\n📊 Running RAGAS evaluation...")
    print("   Using Azure OpenAI as judge LLM\n")

    # Prepare dataset in RAGAS format
    ragas_data = {
        'question': [r['question'] for r in results],
        'answer': [r['answer'] for r in results],
        'contexts': [r['contexts'] for r in results],
        'ground_truth': [r['ground_truth'] for r in results]
    }

    dataset = Dataset.from_dict(ragas_data)

    # Configure Azure OpenAI as judge
    judge_llm = AzureChatOpenAI(
        azure_deployment=AZURE_OPENAI_DEPLOYMENT,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        temperature=0
    )

    judge_embeddings = AzureOpenAIEmbeddings(
        azure_deployment=AZURE_EMBEDDING_DEPLOYMENT,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_KEY,
        api_version=AZURE_OPENAI_API_VERSION
    )

    # Run evaluation
    scores = evaluate(
        dataset=dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall
        ],
        llm=judge_llm,
        embeddings=judge_embeddings
    )

    # Convert to pandas for easy metric extraction
    df = scores.to_pandas()

    return scores, df


# =============================================================================
# SAVE AND DISPLAY RESULTS
# =============================================================================

def display_results(df, results: list[dict]):
    """
    Displays evaluation results in a clean, interview-ready format.
    """

    print("\n" + "=" * 60)
    print("OilMind — RAGAS Evaluation Results")
    print("=" * 60)

    print("\n📊 OVERALL SCORES:")
    print(f"   Faithfulness:      {df['faithfulness'].mean():.3f}")
    print(f"   Answer Relevancy:  {df['answer_relevancy'].mean():.3f}")
    print(f"   Context Precision: {df['context_precision'].mean():.3f}")
    print(f"   Context Recall:    {df['context_recall'].mean():.3f}")

    # Calculate overall average
    avg = (
        df['faithfulness'].mean() +
        df['answer_relevancy'].mean() +
        df['context_precision'].mean() +
        df['context_recall'].mean()
    ) / 4

    print(f"\n   Overall Average:   {avg:.3f}")

    # Category breakdown
    categories = {}
    for r in results:
        cat = r['category']
        if cat not in categories:
            categories[cat] = 0
        categories[cat] += 1

    print(f"\n📋 TEST SET BREAKDOWN:")
    for cat, count in categories.items():
        print(f"   {cat.capitalize()}: {count} questions")

    print(f"\n   Total questions evaluated: {len(results)}")

    print("\n" + "=" * 60)

    # Save results to JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"backend/evaluation/ragas_results_{timestamp}.json"

    output = {
        "timestamp": timestamp,
        "scores": {
            "faithfulness": float(df['faithfulness'].mean()),
            "answer_relevancy": float(df['answer_relevancy'].mean()),
            "context_precision": float(df['context_precision'].mean()),
            "context_recall": float(df['context_recall'].mean()),
            "overall_average": float(avg)
        },
        "test_set_size": len(results),
        "categories": categories
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    # Save detailed CSV
    csv_path = f"backend/evaluation/ragas_results_{timestamp}.csv"
    df.to_csv(csv_path, index=False)

    print(f"\n💾 JSON results saved to: {output_path}")
    print(f"💾 CSV results saved to:  {csv_path}")
    print("\n✅ Evaluation complete")

    return avg


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":

    print("=" * 60)
    print("OilMind — RAGAS Evaluation Pipeline")
    print("=" * 60)

    # Load test set
    test_set_path = os.path.join(
        os.path.dirname(__file__),
        'test_set.json'
    )
    test_cases = load_test_set(test_set_path)
    print(f"\n✅ Loaded {len(test_cases)} test questions")

    # Collect RAG results
    results = collect_rag_results(test_cases)

    # Run RAGAS evaluation
    scores, df = run_ragas_evaluation(results)

    # Display and save results
    avg = display_results(df, results)

    # Final summary line
    print(f"\n🎯 OilMind RAGAS Score Summary:")
    print(f"   Faithfulness:      {df['faithfulness'].mean():.3f}")
    print(f"   Answer Relevancy:  {df['answer_relevancy'].mean():.3f}")
    print(f"   Context Precision: {df['context_precision'].mean():.3f}")
    print(f"   Context Recall:    {df['context_recall'].mean():.3f}")
    print(f"   Overall Average:   {avg:.3f}")