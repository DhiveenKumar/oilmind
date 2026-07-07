# =============================================================================
# indexer.py — Generates embeddings and indexes chunks into Azure AI Search
#
# This file does two things:
# 1. Calls Azure OpenAI to convert each chunk's text into a vector embedding
# 2. Pushes all chunks (text + vector + metadata) into Azure AI Search
#
# After this runs, OilMind's knowledge base is live and searchable.
# =============================================================================

import os
import sys
import time
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SemanticConfiguration,
    SemanticSearch,
    SemanticPrioritizedFields,
    SemanticField
)
from azure.core.credentials import AzureKeyCredential

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from backend.config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_EMBEDDING_DEPLOYMENT,
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_KEY,
    AZURE_SEARCH_INDEX
)
from backend.ingestion.chunker import process_all_documents


# =============================================================================
# STEP 1: Create the Azure AI Search Index Schema
# =============================================================================

def create_search_index(index_client: SearchIndexClient):
    """
    Creates the Azure AI Search index with the correct schema.
    
    Think of this like creating a database table with column definitions
    before inserting any data. The schema defines:
    - What fields each document has
    - Which fields are searchable by keyword
    - Which fields are searchable by vector
    - Which fields are used for semantic re-ranking
    
    We only create the index if it doesn't already exist.
    This means re-running the indexer won't destroy existing data.
    """
    
    # Check if index already exists
    existing_indexes = [idx.name for idx in index_client.list_indexes()]
    if AZURE_SEARCH_INDEX in existing_indexes:
        print(f"✅ Index '{AZURE_SEARCH_INDEX}' already exists — skipping creation")
        return
    
    print(f"📋 Creating index '{AZURE_SEARCH_INDEX}'...")
    
    # Define the fields in our index
    # Think of these as columns in a database table
    fields = [
        
        # chunk_id — The unique identifier for each chunk
        # key=True makes this the primary key — like a database primary key
        # Every document in Azure AI Search must have exactly one key field
        SimpleField(
            name="chunk_id",
            type=SearchFieldDataType.String,
            key=True,
            filterable=True
        ),
        
        # text — The actual chunk content
        # SearchableField means it's included in keyword/BM25 search
        # This is what enables the keyword part of hybrid search
        SearchableField(
            name="text",
            type=SearchFieldDataType.String,
            analyzer_name="en.microsoft"
            # en.microsoft uses Microsoft's English language analyser
            # It handles stemming — "isolating" matches "isolation"
            # Critical for O&G terminology where word forms vary
        ),
        
        # source — Which document this chunk came from
        # filterable=True means we can filter results by document
        # e.g. "only search within ABB_Production_Handbook.pdf"
        SimpleField(
            name="source",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True
        ),
        
        # page_number — Which page this chunk came from
        # Enables citation: "ABB Handbook, Page 47"
        SimpleField(
            name="page_number",
            type=SearchFieldDataType.Int32,
            filterable=True,
            sortable=True
        ),
        
        # chunk_index — Position of this chunk within its page
        SimpleField(
            name="chunk_index",
            type=SearchFieldDataType.Int32,
            filterable=True
        ),
        
        # text_vector — The 3072-dimensional embedding of the chunk text
        # This is what enables semantic/vector search
        # dimensions=3072 must match text-embedding-3-large output exactly
        SearchField(
            name="text_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=3072,
            vector_search_profile_name="oilmind-vector-profile"
            # This profile name connects to the VectorSearch config below
        )
    ]
    
    # Vector search configuration
    # HNSW = Hierarchical Navigable Small World
    # The algorithm that makes vector search fast at scale
    # Think of it as an intelligent graph structure that finds
    # similar vectors without comparing against every single one
    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="oilmind-hnsw",
                # m=4: each node connects to 4 neighbours
                # Higher m = better recall, more memory
                # 4 is the right balance for our corpus size
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="oilmind-vector-profile",
                algorithm_configuration_name="oilmind-hnsw"
            )
        ]
    )
    
    # Semantic search configuration
    # This enables a second pass re-ranking after initial retrieval
    # Azure's semantic ranker re-reads the top results and re-scores
    # them based on deeper language understanding — not just vector similarity
    semantic_config = SemanticConfiguration(
        name="oilmind-semantic-config",
        prioritized_fields=SemanticPrioritizedFields(
            content_fields=[SemanticField(field_name="text")]
            # Tell the semantic ranker to focus on the text field
            # when re-ranking results
        )
    )
    
    # Create the index with all configurations
    index = SearchIndex(
        name=AZURE_SEARCH_INDEX,
        fields=fields,
        vector_search=vector_search,
        semantic_search=SemanticSearch(
            configurations=[semantic_config]
        )
    )
    
    index_client.create_index(index)
    print(f"✅ Index '{AZURE_SEARCH_INDEX}' created successfully")


# =============================================================================
# STEP 2: Generate Embeddings
# =============================================================================

def generate_embedding(text: str, openai_client: AzureOpenAI) -> list[float]:
    """
    Converts a text string into a 3072-dimensional vector embedding.
    
    Why 3072 dimensions?
    text-embedding-3-large produces 3072-dimensional vectors by default.
    Each dimension captures a different aspect of semantic meaning.
    The cosine similarity between two vectors tells us how semantically
    similar the two texts are — 1.0 = identical meaning, 0.0 = unrelated.
    
    This is called at index time for every chunk AND at query time
    for every incoming question — so the chunk and query live in the
    same vector space and can be compared directly.
    """
    
    response = openai_client.embeddings.create(
        model=AZURE_EMBEDDING_DEPLOYMENT,
        input=text
    )
    
    return response.data[0].embedding


# =============================================================================
# STEP 3: Index All Chunks
# =============================================================================

def index_chunks(
    chunks: list[dict],
    search_client: SearchClient,
    openai_client: AzureOpenAI
):
    """
    Takes all chunks from chunker.py, generates an embedding for each,
    and uploads everything to Azure AI Search in batches.
    
    Why batches?
    The Azure AI Search SDK has a limit on how many documents
    you can upload in a single API call. We use batches of 50
    to stay well within limits while being efficient.
    
    Why sleep between embedding calls?
    Azure OpenAI has rate limits — a maximum number of API calls
    per minute. If we call too fast, we get rate limit errors.
    A small sleep between calls keeps us within limits.
    In production with higher rate limit tiers, you'd remove this
    or implement exponential backoff instead.
    """
    
    print(f"\n🔄 Generating embeddings and indexing {len(chunks)} chunks...")
    print(f"   This will take a few minutes — embedding each chunk via Azure OpenAI\n")
    
    documents_to_index = []
    
    for i, chunk in enumerate(chunks):
        
        # Progress indicator — show every 50 chunks
        if i % 50 == 0:
            print(f"   Processing chunk {i+1}/{len(chunks)}...")
        
        # Generate embedding for this chunk's text
        embedding = generate_embedding(chunk["text"], openai_client)
        
        # Build the document object matching our index schema exactly
        document = {
            "chunk_id": chunk["chunk_id"],
            "text": chunk["text"],
            "source": chunk["source"],
            "page_number": chunk["page_number"],
            "chunk_index": chunk["chunk_index"],
            "text_vector": embedding  # The 3072-dimensional vector
        }
        
        documents_to_index.append(document)
        
        # Small pause to respect Azure OpenAI rate limits
        # 0.1 seconds = 10 embedding calls per second max
        time.sleep(0.1)
        
        # Upload in batches of 50
        if len(documents_to_index) >= 50:
            search_client.upload_documents(documents=documents_to_index)
            documents_to_index = []  # Reset batch
    
    # Upload any remaining documents in the last partial batch
    if documents_to_index:
        search_client.upload_documents(documents=documents_to_index)
    
    print(f"\n✅ All {len(chunks)} chunks indexed into Azure AI Search")
    print(f"   Index name: {AZURE_SEARCH_INDEX}")
    print(f"   OilMind knowledge base is now live and searchable\n")


# =============================================================================
# MAIN — Orchestrates the full indexing pipeline
# =============================================================================

def run_indexing_pipeline():
    """
    Master function that runs the complete ingestion pipeline:
    1. Process all PDFs into chunks (calls chunker.py)
    2. Create the Azure AI Search index schema
    3. Generate embeddings for all chunks
    4. Upload everything to Azure AI Search
    """
    
    print("=" * 60)
    print("OilMind — Indexing Pipeline")
    print("=" * 60)
    
    # Initialise Azure OpenAI client
    openai_client = AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_KEY,
        api_version=AZURE_OPENAI_API_VERSION
    )
    
    # Initialise Azure AI Search clients
    # Two clients — one for index management, one for document operations
    credential = AzureKeyCredential(AZURE_SEARCH_KEY)
    
    index_client = SearchIndexClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        credential=credential
    )
    
    search_client = SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_INDEX,
        credential=credential
    )
    
    # Step 1: Process PDFs into chunks
    corpus_dir = os.path.join(
        os.path.dirname(__file__),
        '..', '..', 'corpus', 'raw'
    )
    chunks = process_all_documents(corpus_dir)
    
    # Step 2: Create index schema
    create_search_index(index_client)
    
    # Step 3 + 4: Generate embeddings and index
    index_chunks(chunks, search_client, openai_client)
    
    print("=" * 60)
    print("✅ Indexing pipeline complete")
    print(f"   {len(chunks)} chunks are now searchable in Azure AI Search")
    print("   OilMind is ready to answer oil & gas questions")
    print("=" * 60)


if __name__ == "__main__":
    run_indexing_pipeline()