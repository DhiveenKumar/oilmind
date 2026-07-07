# =============================================================================
# main.py — FastAPI backend for OilMind
#
# Exposes three endpoints:
# GET  /          → Health check — is the service running?
# GET  /health    → Detailed health check — are all Azure services reachable?
# POST /query     → Main endpoint — takes a question, returns cited answer
#
# Why FastAPI over Flask?
# 1. Async support — multiple concurrent requests without blocking
# 2. Automatic API documentation at /docs — team can test without Postman
# 3. Built-in request/response validation via Pydantic models
# 4. Production-ready with uvicorn ASGI server
# =============================================================================

import os
import sys
import time
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.config import validate_config, APPLICATIONINSIGHTS_CONNECTION_STRING
from backend.agent.router import oilmind_query

# =============================================================================
# LOGGING SETUP
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("oilmind")

# =============================================================================
# APPLICATION INSIGHTS TELEMETRY
# =============================================================================

# Initialise Application Insights if connection string is available
# This sends every request's latency, status, and metadata to Azure Monitor
try:
    if (APPLICATIONINSIGHTS_CONNECTION_STRING and
            APPLICATIONINSIGHTS_CONNECTION_STRING != "placeholder"):
        from opencensus.ext.azure.log_exporter import AzureLogHandler
        logger.addHandler(
            AzureLogHandler(
                connection_string=APPLICATIONINSIGHTS_CONNECTION_STRING
            )
        )
        logger.info("Application Insights telemetry enabled")
except Exception as e:
    logger.warning(f"Application Insights not configured: {e}")

# =============================================================================
# FASTAPI APP INITIALISATION
# =============================================================================

app = FastAPI(
    title="OilMind API",
    description="""
    Agentic RAG system for Oil & Gas Operations at ChampionX.
    
    Allows field engineers and operations teams to query technical 
    documentation — equipment manuals, safety procedures, regulatory 
    standards — using natural language and receive cited answers.
    """,
    version="1.0.0",
    docs_url="/docs"  # Interactive API docs available at /docs
)

# CORS middleware — allows Streamlit frontend to call this API
# In production, restrict origins to your specific frontend URL
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# REQUEST AND RESPONSE MODELS
# =============================================================================

class QueryRequest(BaseModel):
    """
    Validates incoming query requests.
    
    Pydantic automatically validates that:
    - query is a non-empty string
    - include_trace is a boolean (defaults to False)
    
    If validation fails, FastAPI returns a 422 error automatically
    before our code even runs — no manual validation needed.
    """
    query: str
    include_trace: Optional[bool] = False


class QueryResponse(BaseModel):
    """
    Defines the structure of every response from /query endpoint.
    
    Having a defined response model means:
    - Streamlit knows exactly what fields to expect
    - The /docs page shows the response schema automatically
    - Adding new fields is a one-line change
    """
    answer: str
    sources: list[str]
    chunks_retrieved: int
    query_type: str
    latency_seconds: float
    reasoning_trace: Optional[list[str]] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    services: dict


# =============================================================================
# STARTUP EVENT
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """
    Runs once when the FastAPI application starts.
    
    Why validate config at startup?
    Same pre-flight checklist principle from config.py —
    catch missing credentials immediately when the service starts,
    not when the first field engineer sends a query at 2am.
    """
    logger.info("OilMind API starting up...")
    try:
        validate_config()
        logger.info("✅ Configuration validated")
        logger.info("✅ OilMind API ready to serve requests")
    except ValueError as e:
        logger.error(f"❌ Configuration error: {e}")
        raise


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/", response_model=dict)
async def root():
    """
    Basic health check — confirms the service is running.
    Used by Azure App Service to verify the container is alive.
    """
    return {
        "service": "OilMind API",
        "status": "running",
        "version": "1.0.0",
        "description": "Agentic RAG for Oil & Gas Operations"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Detailed health check — verifies all Azure services are reachable.
    
    Why a separate /health endpoint from /?
    The root endpoint just confirms FastAPI is running.
    The /health endpoint actively tests downstream dependencies.
    Azure App Service uses / for liveness checks (is the container alive?).
    Monitoring systems use /health for readiness checks
    (are all dependencies working?).
    These are different questions with different answers.
    """
    from openai import AzureOpenAI
    from azure.search.documents import SearchClient
    from azure.core.credentials import AzureKeyCredential
    from backend.config import (
        AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY,
        AZURE_OPENAI_API_VERSION, AZURE_EMBEDDING_DEPLOYMENT,
        AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY, AZURE_SEARCH_INDEX
    )

    services = {}

    # Test Azure OpenAI
    try:
        client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
            api_version=AZURE_OPENAI_API_VERSION
        )
        client.embeddings.create(
            model=AZURE_EMBEDDING_DEPLOYMENT,
            input="health check"
        )
        services["azure_openai"] = "healthy"
    except Exception as e:
        services["azure_openai"] = f"unhealthy: {str(e)[:50]}"

    # Test Azure AI Search
    try:
        search_client = SearchClient(
            endpoint=AZURE_SEARCH_ENDPOINT,
            index_name=AZURE_SEARCH_INDEX,
            credential=AzureKeyCredential(AZURE_SEARCH_KEY)
        )
        search_client.get_document_count()
        services["azure_search"] = "healthy"
    except Exception as e:
        services["azure_search"] = f"unhealthy: {str(e)[:50]}"

    overall_status = (
        "healthy"
        if all("healthy" == v for v in services.values())
        else "degraded"
    )

    return HealthResponse(
        status=overall_status,
        version="1.0.0",
        services=services
    )


@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    """
    Main endpoint — the core of OilMind.
    
    Receives a natural language question, routes it through
    the LangGraph agent, and returns a cited answer.
    
    Every request is:
    1. Validated by Pydantic automatically
    2. Timed for latency tracking
    3. Logged to Application Insights
    4. Returned with full source citations
    
    Why async?
    FastAPI with async endpoints can handle multiple concurrent
    requests without blocking. When one request is waiting for
    Azure OpenAI to respond, other requests can be processed.
    Critical for a tool serving multiple field engineers
    simultaneously across different sites.
    """

    # Validate query is not empty
    if not request.query.strip():
        raise HTTPException(
            status_code=400,
            detail="Query cannot be empty"
        )

    # Track latency
    start_time = time.time()

    logger.info(f"Query received: {request.query[:100]}")

    try:
        # Route through LangGraph agent
        result = oilmind_query(request.query)

        latency = round(time.time() - start_time, 2)

        # Log to Application Insights
        logger.info(
            f"Query completed | "
            f"type={result['query_type']} | "
            f"chunks={result['chunks_retrieved']} | "
            f"latency={latency}s | "
            f"sources={len(result['sources'])}"
        )

        return QueryResponse(
            answer=result["answer"],
            sources=result["sources"],
            chunks_retrieved=result["chunks_retrieved"],
            query_type=result["query_type"],
            latency_seconds=latency,
            reasoning_trace=(
                result.get("reasoning_trace")
                if request.include_trace
                else None
            )
        )

    except Exception as e:
        latency = round(time.time() - start_time, 2)
        logger.error(f"Query failed after {latency}s: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Query processing failed: {str(e)}"
        )