# 🛢️ OilMind — Agentic RAG for Oil & Gas Operations

> An enterprise-grade Agentic RAG system built at ChampionX that allows field engineers and operations teams to query technical documentation using natural language and receive accurate, cited answers in seconds.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Azure%20App%20Service-blue)](https://oilmind-app-b4azbghpe2ajahcs.eastus-01.azurewebsites.net)
[![Python](https://img.shields.io/badge/Python-3.12-green)](https://python.org)
[![Azure OpenAI](https://img.shields.io/badge/Azure-OpenAI%20GPT--4o-orange)](https://azure.microsoft.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic%20RAG-purple)](https://github.com/langchain-ai/langgraph)

---

## 🎯 Problem Statement

Field engineers and operations teams in oil and gas spend 30-45 minutes manually searching through hundreds of equipment manuals, safety procedures, and regulatory documents to answer operational questions. In a safety-critical environment, slow or incorrect answers have real consequences.

**OilMind solves this** — natural language queries answered in seconds with full source citations.

---

## 🏗️ Architecture
User Query
↓
Streamlit Frontend (port 8501)
↓ HTTP POST /query
FastAPI Backend (port 8000)
↓
LangGraph Agentic Router
↓                    ↓
Simple RAG          Reflection Agent
(single pass)       (ReAct loop, 3 iterations)
↓                    ↓
Azure AI Search (Hybrid: BM25 + Vector)
↓
Azure OpenAI GPT-4o (generation)
Azure OpenAI text-embedding-3-large (retrieval)
↓
Cited Answer + Source Documents

---

## 🚀 Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **LLM** | Azure OpenAI GPT-4o | Answer generation |
| **Embeddings** | text-embedding-3-large (3072-dim) | Semantic search |
| **Retrieval** | Azure AI Search (Hybrid) | BM25 + Vector search |
| **Agent** | LangGraph StateGraph | Query routing + ReAct loop |
| **Backend** | FastAPI + Uvicorn | REST API, async |
| **Frontend** | Streamlit | Field engineer UI |
| **Container** | Docker (multi-stage) | Packaging |
| **Registry** | Azure Container Registry | Image storage |
| **Hosting** | Azure App Service | Production deployment |
| **Secrets** | Azure Key Vault | Credential management |
| **Monitoring** | Application Insights | Telemetry + alerting |
| **CI/CD** | GitHub Actions | Automated deployment |
| **Evaluation** | RAGAS | Quality metrics |

---

## 📊 Evaluation Results

Evaluated on a 25-question oil and gas domain test set across 4 categories:
regulatory, safety, procedural, and technical.

| Metric | Score |
|---|---|
| **Faithfulness** | 0.770 |
| **Answer Relevancy** | 0.740 |
| **Context Precision** | 0.570 |
| **Context Recall** | 0.667 |
| **Overall Average** | 0.687 |

---

## 📁 Knowledge Base

| Document | Pages | Chunks |
|---|---|---|
| ABB Oil & Gas Production Handbook | 108 | 458 |
| IOGP Life Saving Rules | 24 | 86 |
| OSHA H2S FatalFacts | 3 | 24 |
| **Total** | **135** | **568** |

---

## 🤖 Agent Architecture

OilMind uses a LangGraph StateGraph with two retrieval paths:

**Simple RAG** — for direct factual and procedural questions
- Single hybrid search pass
- Top 5 chunks retrieved
- GPT-4o generation at temperature 0
- Average latency: 6-8 seconds

**Reflection Agent (ReAct)** — for complex multi-part questions
- Query decomposition into 2-4 sub-questions
- Up to 3 retrieval iterations
- Self-evaluation of information sufficiency
- Cross-document synthesis
- Average latency: 60-90 seconds

---

## 🛠️ Project Structure
oilmind/
├── backend/
│   ├── agent/
│   │   ├── router.py           # LangGraph StateGraph + classifier
│   │   ├── simple_rag.py       # Hybrid retrieval + GPT-4o
│   │   └── reflection_agent.py # ReAct loop with decomposition
│   ├── ingestion/
│   │   ├── chunker.py          # PDF → 512-token chunks
│   │   └── indexer.py          # Embeddings → Azure AI Search
│   ├── evaluation/
│   │   ├── run_ragas.py        # RAGAS evaluation pipeline
│   │   └── test_set.json       # 25 O&G domain questions
│   ├── main.py                 # FastAPI + health checks
│   ├── config.py               # Centralised configuration
│   └── requirements.txt
├── frontend/
│   └── app.py                  # Streamlit UI
├── corpus/raw/                 # Source PDFs
├── .github/workflows/
│   └── deploy.yml              # CI/CD pipeline
├── Dockerfile                  # Multi-stage build
├── docker-compose.yml          # Local development
└── start.sh                    # Container startup

---

## ⚙️ Key Design Decisions

**Why hybrid search over pure vector search?**
Oil and gas queries have two patterns: exact regulatory references (API 510, OSHA 1910.146) need keyword matching; informal operational questions need semantic understanding. Hybrid search handles both.

**Why LangGraph over plain LangChain?**
Stateful agent orchestration — LangGraph maintains state across agent steps, enabling the reflection agent's multi-iteration reasoning loop. Plain chains are stateless.

**Why temperature 0 for generation?**
Safety-critical environment. Field engineers may act on answers. Deterministic generation ensures the same question always gets the same correct answer.

**Why multi-stage Docker build?**
Build tools (gcc, g++) needed to compile pymupdf are not present in the production image. Smaller, more secure final image.

---

## 📈 Monitoring

Every query logged to Azure Application Insights:
- Query type (simple/complex)
- Latency (seconds)
- Chunks retrieved
- Sources used
- Success/failure

---

## 🔒 Security

- All secrets in Azure Key Vault
- Managed identity for service-to-service auth
- No credentials in codebase or Docker image
- Environment variables injected at runtime

---

## 📝 License

Internal ChampionX project. Not for public distribution.