# =============================================================================
# config.py — Central configuration for OilMind
# Loads all secrets from .env file (development) 
# In production: secrets come from Azure Key Vault via managed identity
# =============================================================================

import os
from dotenv import load_dotenv

# Load .env file — this line reads your .env file and makes all 
# variables available via os.environ
# In production on Azure App Service, environment variables are 
# set directly — load_dotenv() simply finds nothing to load and 
# continues, so the same code works in both environments
load_dotenv()

# =============================================================================
# AZURE OPENAI SETTINGS
# =============================================================================

# The URL of your Azure OpenAI resource
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")

# The API key for authenticating to Azure OpenAI
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")

# The name you gave your GPT-4o deployment inside Azure OpenAI Studio
# We named it "gpt-4o" — this must match exactly
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

# The name you gave your embedding model deployment
# We named it "text-embedding-3-large" — this must match exactly
AZURE_EMBEDDING_DEPLOYMENT = os.getenv(
    "AZURE_EMBEDDING_DEPLOYMENT", 
    "text-embedding-3-large"
)

# Azure OpenAI API version — this is the version of the API specification
# Always pin this to a specific version, never use "latest"
# because API behaviour can change between versions
AZURE_OPENAI_API_VERSION = "2024-08-01-preview"

# =============================================================================
# AZURE AI SEARCH SETTINGS
# =============================================================================

# The URL of your Azure AI Search resource
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")

# The admin key for authenticating to Azure AI Search
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")

# The name of the search index where document chunks are stored
# Think of this like a database table name
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", "oilmind-index")

# =============================================================================
# AZURE KEY VAULT SETTINGS
# =============================================================================

# The URL of your Key Vault — used in production for secret retrieval
AZURE_KEYVAULT_URL = os.getenv("AZURE_KEYVAULT_URL")

# =============================================================================
# APPLICATION INSIGHTS SETTINGS
# =============================================================================

# Connection string for sending telemetry to Application Insights
APPLICATIONINSIGHTS_CONNECTION_STRING = os.getenv(
    "APPLICATIONINSIGHTS_CONNECTION_STRING"
)

# =============================================================================
# VALIDATION — Check all critical settings are present at startup
# =============================================================================

def validate_config():
    """
    Validates that all required configuration values are present.
    Called once when the application starts.
    
    Why validate at startup rather than at the point of use?
    Because a missing key discovered mid-request causes a confusing 
    error deep inside the code. A startup validation fails immediately 
    and clearly — like a pre-flight checklist before takeoff.
    This is standard production practice.
    """
    
    required_settings = {
        "AZURE_OPENAI_ENDPOINT": AZURE_OPENAI_ENDPOINT,
        "AZURE_OPENAI_KEY": AZURE_OPENAI_KEY,
        "AZURE_SEARCH_ENDPOINT": AZURE_SEARCH_ENDPOINT,
        "AZURE_SEARCH_KEY": AZURE_SEARCH_KEY,
    }
    
    missing = []
    for name, value in required_settings.items():
        if not value:
            missing.append(name)
    
    if missing:
        raise ValueError(
            f"Missing required configuration: {', '.join(missing)}\n"
            f"Check your .env file or Azure App Service environment variables."
        )
    
    print("✅ Configuration validated successfully")
    print(f"   OpenAI Endpoint: {AZURE_OPENAI_ENDPOINT}")
    print(f"   Search Endpoint: {AZURE_SEARCH_ENDPOINT}")
    print(f"   Search Index:    {AZURE_SEARCH_INDEX}")


# =============================================================================
# CHUNK SETTINGS — Controls how PDFs are split into pieces
# =============================================================================

# How many tokens per chunk
# 512 is the sweet spot — large enough to contain a complete procedure step,
# small enough that retrieval stays precise
CHUNK_SIZE = 512

# How many tokens overlap between consecutive chunks
# Overlap ensures a concept that spans a chunk boundary 
# is not lost — like a Venn diagram between adjacent chunks
CHUNK_OVERLAP = 50

# How many chunks to retrieve per query before re-ranking
# We retrieve 5, then GPT-4o uses the most relevant ones
TOP_K_RESULTS = 5