# =============================================================================
# chunker.py — Reads oil & gas PDFs and splits them into searchable chunks
#
# Why chunking matters:
# LLMs have context limits — you cannot feed a 300-page handbook into GPT-4o
# in one shot. Chunking breaks documents into precise, retrievable pieces.
# Each chunk is small enough to be retrieved accurately but large enough
# to contain a complete thought or procedure step.
# =============================================================================

import os
import sys

# PyMuPDF — fastest Python PDF parser, handles complex O&G document layouts
import fitz  

# LangChain's text splitter — handles token-aware chunking with overlap
from langchain.text_splitter import RecursiveCharacterTextSplitter

# Import our centralised config — chunk size and overlap defined there
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from backend.config import CHUNK_SIZE, CHUNK_OVERLAP


def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """
    Reads a PDF file page by page and extracts raw text with page metadata.
    
    Why page by page and not all at once?
    Because we need to know WHICH PAGE each chunk came from.
    When OilMind tells a field engineer "see ABB Handbook Page 47",
    that page number comes from here — extracted at the source.
    
    Args:
        pdf_path: Full path to the PDF file
        
    Returns:
        List of dicts, one per page:
        [
            {"page_number": 1, "text": "...", "source": "ABB_Production_Handbook.pdf"},
            {"page_number": 2, "text": "...", "source": "ABB_Production_Handbook.pdf"},
            ...
        ]
    """
    
    # Extract just the filename for citations
    # e.g. "/workspaces/oilmind/corpus/raw/ABB_Production_Handbook.pdf"
    # becomes "ABB_Production_Handbook.pdf"
    filename = os.path.basename(pdf_path)
    
    pages = []
    
    # Open the PDF using PyMuPDF
    # fitz is PyMuPDF's internal name — named after the PDF spec "PDF 1.x"
    doc = fitz.open(pdf_path)
    
    print(f"📄 Reading: {filename} ({len(doc)} pages)")
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # Extract text from this page
        # "text" flag gives us clean plain text
        text = page.get_text("text")
        
        # Skip pages with very little text
        # Some PDF pages are just images, diagrams, or blank pages
        # 50 characters is roughly one short sentence — anything less
        # is not worth indexing and would create noise in retrieval
        if len(text.strip()) < 50:
            continue
            
        pages.append({
            "page_number": page_num + 1,  # Human readable — page 1 not page 0
            "text": text.strip(),
            "source": filename
        })
    
    doc.close()
    
    print(f"   ✅ Extracted {len(pages)} pages with content")
    return pages


def chunk_pages(pages: list[dict]) -> list[dict]:
    """
    Takes extracted pages and splits them into chunks of CHUNK_SIZE tokens
    with CHUNK_OVERLAP token overlap between consecutive chunks.
    
    Why RecursiveCharacterTextSplitter?
    It tries to split on natural boundaries first — paragraphs, then sentences,
    then words — rather than cutting blindly at character count.
    This means chunks break at logical points, preserving complete thoughts.
    For oil and gas procedures, this is critical — a procedure step should
    not be cut mid-instruction.
    
    Args:
        pages: List of page dicts from extract_text_from_pdf()
        
    Returns:
        List of chunk dicts with full metadata attached:
        [
            {
                "chunk_id": "ABB_Production_Handbook.pdf_p1_c0",
                "text": "...",
                "source": "ABB_Production_Handbook.pdf",
                "page_number": 1,
                "chunk_index": 0
            },
            ...
        ]
    """
    
    # Initialise the text splitter with our configured values
    # chunk_size: maximum tokens per chunk (512)
    # chunk_overlap: tokens shared between consecutive chunks (50)
    # separators: try splitting on these in order — paragraph, newline, space
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", " ", ""],
        length_function=len
    )
    
    all_chunks = []
    
    for page in pages:
        # Split this page's text into chunks
        texts = splitter.split_text(page["text"])
        
        for chunk_index, chunk_text in enumerate(texts):
            
            # Create a unique ID for every chunk
            # Format: filename_pageNumber_chunkIndex
            # e.g. "ABB_Production_Handbook.pdf_p1_c0"
            # This ID is used in Azure AI Search as the document key
            chunk_id = (
                f"{page['source'].replace('.', '_')}"
                f"_p{page['page_number']}"
                f"_c{chunk_index}"
            )
            
            all_chunks.append({
                "chunk_id": chunk_id,
                "text": chunk_text,
                "source": page["source"],
                "page_number": page["page_number"],
                "chunk_index": chunk_index
            })
    
    return all_chunks


def process_all_documents(corpus_dir: str) -> list[dict]:
    """
    Master function — processes every PDF in the corpus directory.
    
    This is the only function called from outside this file.
    It orchestrates the full pipeline:
    1. Find all PDFs in corpus/raw/
    2. Extract text from each
    3. Chunk each document
    4. Return all chunks combined
    
    Args:
        corpus_dir: Path to the folder containing PDFs
        
    Returns:
        All chunks from all documents combined into one list
    """
    
    all_chunks = []
    
    # Find every PDF in the corpus directory
    pdf_files = [
        f for f in os.listdir(corpus_dir) 
        if f.endswith('.pdf')
    ]
    
    if not pdf_files:
        raise ValueError(f"No PDF files found in {corpus_dir}")
    
    print(f"\n🗂️  Found {len(pdf_files)} documents to process:")
    for f in pdf_files:
        print(f"   - {f}")
    print()
    
    # Process each PDF
    for pdf_file in pdf_files:
        pdf_path = os.path.join(corpus_dir, pdf_file)
        
        # Step 1: Extract text page by page
        pages = extract_text_from_pdf(pdf_path)
        
        # Step 2: Split pages into chunks
        chunks = chunk_pages(pages)
        
        print(f"   📦 Created {len(chunks)} chunks from {pdf_file}")
        
        all_chunks.extend(chunks)
    
    print(f"\n✅ Total chunks created: {len(all_chunks)}")
    print(f"   Ready for indexing into Azure AI Search\n")
    
    return all_chunks


# =============================================================================
# TEST — Run this file directly to verify chunking works
# =============================================================================

if __name__ == "__main__":
    
    # Path to your corpus
    corpus_dir = os.path.join(
        os.path.dirname(__file__), 
        '..', '..', 'corpus', 'raw'
    )
    
    print("=" * 60)
    print("OilMind — Document Chunker Test")
    print("=" * 60)
    
    # Process all documents
    chunks = process_all_documents(corpus_dir)
    
    # Show a sample chunk so you can verify quality
    if chunks:
        print("=" * 60)
        print("SAMPLE CHUNK — verify this looks correct:")
        print("=" * 60)
        sample = chunks[10]  # Show chunk 10 — skip first few which may be cover pages
        print(f"Chunk ID:    {sample['chunk_id']}")
        print(f"Source:      {sample['source']}")
        print(f"Page:        {sample['page_number']}")
        print(f"Text preview: {sample['text'][:300]}...")
        print()
        print(f"Total chunks ready for Azure AI Search: {len(chunks)}")