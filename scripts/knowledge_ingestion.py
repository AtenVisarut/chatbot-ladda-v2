"""
Knowledge Ingestion System
==========================
ระบบนำเข้าความรู้จากหลายแหล่งข้อมูลเข้า Supabase knowledge table

รองรับ:
1. CSV/Excel files - ข้อมูลโรคพืช, ศัตรูพืช, วิธีการดูแล
2. Website URLs - ดึงข้อมูลจากเว็บไซต์
3. PDF Documents - สกัดข้อความจากไฟล์ PDF

การใช้งาน:
    # Import จาก CSV
    python knowledge_ingestion.py --csv "data/diseases.csv"

    # Import จาก URL
    python knowledge_ingestion.py --url "https://example.com/article"

    # Import จาก PDF
    python knowledge_ingestion.py --pdf "data/manual.pdf"

    # Import ทั้งโฟลเดอร์
    python knowledge_ingestion.py --folder "data/knowledge" --type csv
"""

import os
import sys
import csv
import json
import asyncio
import argparse
import logging
from typing import List, Dict, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Chunk settings for text splitting
CHUNK_SIZE = 1000  # characters per chunk
CHUNK_OVERLAP = 200  # overlap between chunks

# =============================================================================
# Initialize Clients
# =============================================================================

def get_supabase_client():
    """Initialize Supabase client"""
    try:
        from supabase import create_client
        if not SUPABASE_URL or not SUPABASE_KEY:
            logger.error("SUPABASE_URL or SUPABASE_KEY not set")
            return None
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        return None

def get_openai_client():
    """Initialize OpenAI client for embeddings"""
    try:
        from openai import OpenAI
        if not OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY not set")
            return None
        return OpenAI(api_key=OPENAI_API_KEY)
    except Exception as e:
        logger.error(f"Failed to create OpenAI client: {e}")
        return None

# =============================================================================
# Text Processing Utilities
# =============================================================================

def split_text_into_chunks(text: str, chunk_size: int = CHUNK_SIZE,
                           overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Split text into overlapping chunks for better retrieval

    Args:
        text: The text to split
        chunk_size: Maximum characters per chunk
        overlap: Number of characters to overlap between chunks

    Returns:
        List of text chunks
    """
    if not text or len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Try to find a natural break point (sentence or paragraph)
        if end < len(text):
            # Look for paragraph break
            para_break = text.rfind('\n\n', start, end)
            if para_break > start + chunk_size // 2:
                end = para_break + 2
            else:
                # Look for sentence break
                for sep in ['. ', '。', '! ', '? ', '\n']:
                    sent_break = text.rfind(sep, start, end)
                    if sent_break > start + chunk_size // 2:
                        end = sent_break + len(sep)
                        break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap

    return chunks

def clean_text(text: str) -> str:
    """Clean and normalize text"""
    if not text:
        return ""

    import re

    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)

    # Remove special characters but keep Thai
    text = re.sub(r'[^\w\s\u0E00-\u0E7Fก-๙.,!?;:\-()"\']', '', text)

    # Fix Thai encoding issues
    text = text.replace('Ğ', '')
    text = text.replace('\x00', '')

    return text.strip()

# =============================================================================
# Embedding Generation
# =============================================================================

def generate_embedding(text: str, openai_client) -> Optional[List[float]]:
    """
    Generate embedding vector for text using OpenAI

    Args:
        text: Text to embed
        openai_client: OpenAI client instance

    Returns:
        List of floats representing the embedding vector
    """
    try:
        response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            encoding_format="float"
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        return None

# =============================================================================
# CSV/Excel Importer
# =============================================================================

def load_csv(file_path: str) -> List[Dict]:
    """
    Load knowledge from CSV file

    Expected CSV columns:
    - title: หัวข้อ/ชื่อโรค/ชื่อศัตรูพืช
    - content: เนื้อหา/รายละเอียด
    - category: หมวดหมู่ (disease, pest, crop_care, etc.)
    - plant_type: ชนิดพืช (optional)
    - source: แหล่งที่มา (optional)
    """
    documents = []

    try:
        # Detect encoding
        encodings = ['utf-8', 'utf-8-sig', 'cp874', 'tis-620']

        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        doc = {
                            'title': row.get('title', '').strip(),
                            'content': row.get('content', '').strip(),
                            'category': row.get('category', 'general').strip(),
                            'plant_type': row.get('plant_type', '').strip(),
                            'source': row.get('source', file_path).strip(),
                            'metadata': {
                                'file': file_path,
                                'row': reader.line_num
                            }
                        }

                        # Skip empty rows
                        if doc['title'] or doc['content']:
                            documents.append(doc)

                    logger.info(f"✓ Loaded {len(documents)} documents from {file_path} ({encoding})")
                    break

            except UnicodeDecodeError:
                continue

        if not documents:
            logger.warning(f"Could not read {file_path} with any encoding")

    except Exception as e:
        logger.error(f"Failed to load CSV {file_path}: {e}")

    return documents

def load_excel(file_path: str) -> List[Dict]:
    """Load knowledge from Excel file"""
    documents = []

    try:
        import pandas as pd

        df = pd.read_excel(file_path)

        for idx, row in df.iterrows():
            doc = {
                'title': str(row.get('title', '')).strip() if pd.notna(row.get('title')) else '',
                'content': str(row.get('content', '')).strip() if pd.notna(row.get('content')) else '',
                'category': str(row.get('category', 'general')).strip() if pd.notna(row.get('category')) else 'general',
                'plant_type': str(row.get('plant_type', '')).strip() if pd.notna(row.get('plant_type')) else '',
                'source': str(row.get('source', file_path)).strip() if pd.notna(row.get('source')) else file_path,
                'metadata': {
                    'file': file_path,
                    'row': idx + 1
                }
            }

            if doc['title'] or doc['content']:
                documents.append(doc)

        logger.info(f"✓ Loaded {len(documents)} documents from {file_path}")

    except ImportError:
        logger.error("pandas and openpyxl required for Excel. Install with: pip install pandas openpyxl")
    except Exception as e:
        logger.error(f"Failed to load Excel {file_path}: {e}")

    return documents

# =============================================================================
# Website Scraper
# =============================================================================

def scrape_website(url: str, selector: str = None) -> List[Dict]:
    """
    Scrape content from website URL

    Args:
        url: Website URL to scrape
        selector: CSS selector to target specific content (optional)

    Returns:
        List of document dictionaries
    """
    documents = []

    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        # Detect encoding
        if response.encoding == 'ISO-8859-1':
            response.encoding = response.apparent_encoding

        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        # Get title
        title = soup.find('title')
        title_text = title.get_text().strip() if title else url

        # Get content
        if selector:
            content_elem = soup.select(selector)
            content = ' '.join([elem.get_text() for elem in content_elem])
        else:
            # Try common content selectors
            content_selectors = [
                'article', 'main', '.content', '#content',
                '.post-content', '.entry-content', '.article-body'
            ]
            content = ""
            for sel in content_selectors:
                elem = soup.select_one(sel)
                if elem:
                    content = elem.get_text()
                    break

            if not content:
                # Fallback to body
                body = soup.find('body')
                content = body.get_text() if body else soup.get_text()

        content = clean_text(content)

        if content:
            doc = {
                'title': title_text,
                'content': content,
                'category': 'web_article',
                'plant_type': '',
                'source': url,
                'metadata': {
                    'url': url,
                    'scraped_at': str(asyncio.get_event_loop().time()) if asyncio.get_event_loop().is_running() else ''
                }
            }
            documents.append(doc)
            logger.info(f"✓ Scraped {len(content)} characters from {url}")
        else:
            logger.warning(f"No content found at {url}")

    except ImportError:
        logger.error("requests and beautifulsoup4 required. Install with: pip install requests beautifulsoup4")
    except Exception as e:
        logger.error(f"Failed to scrape {url}: {e}")

    return documents

# =============================================================================
# PDF Loader
# =============================================================================

def load_pdf(file_path: str) -> List[Dict]:
    """
    Extract text from PDF file

    Args:
        file_path: Path to PDF file

    Returns:
        List of document dictionaries (one per page or section)
    """
    documents = []

    try:
        import fitz  # PyMuPDF

        doc = fitz.open(file_path)

        full_text = ""
        for page_num, page in enumerate(doc, 1):
            text = page.get_text()
            full_text += f"\n\n--- หน้า {page_num} ---\n\n{text}"

        doc.close()

        # Clean text
        full_text = clean_text(full_text)

        # Get filename as title
        title = Path(file_path).stem

        if full_text:
            document = {
                'title': title,
                'content': full_text,
                'category': 'pdf_document',
                'plant_type': '',
                'source': file_path,
                'metadata': {
                    'file': file_path,
                    'pages': len(list(fitz.open(file_path)))
                }
            }
            documents.append(document)
            logger.info(f"✓ Extracted {len(full_text)} characters from {file_path}")

    except ImportError:
        logger.error("PyMuPDF required for PDF. Install with: pip install pymupdf")
    except Exception as e:
        logger.error(f"Failed to load PDF {file_path}: {e}")

    return documents

# =============================================================================
# Supabase Uploader
# =============================================================================

def upload_to_supabase(documents: List[Dict], supabase_client, openai_client,
                       batch_size: int = 10) -> int:
    """
    Upload documents to Supabase knowledge table with embeddings

    Args:
        documents: List of document dictionaries
        supabase_client: Supabase client
        openai_client: OpenAI client for embeddings
        batch_size: Number of documents per batch

    Returns:
        Number of successfully uploaded documents
    """
    uploaded = 0

    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        records = []

        for doc in batch:
            # Combine title and content for embedding
            embed_text = f"{doc['title']}\n\n{doc['content']}"

            # Generate embedding
            embedding = generate_embedding(embed_text[:8000], openai_client)

            if embedding:
                record = {
                    'title': doc['title'][:500],  # Limit title length
                    'content': doc['content'][:10000],  # Limit content length
                    'category': doc.get('category', 'general'),
                    'plant_type': doc.get('plant_type', ''),
                    'source': doc.get('source', ''),
                    'metadata': json.dumps(doc.get('metadata', {})),
                    'embedding': embedding
                }
                records.append(record)

        if records:
            try:
                result = supabase_client.table('knowledge').insert(records).execute()
                uploaded += len(records)
                logger.info(f"✓ Uploaded batch {i//batch_size + 1}: {len(records)} documents")
            except Exception as e:
                logger.error(f"Failed to upload batch: {e}")

    return uploaded

# =============================================================================
# Main Functions
# =============================================================================

def process_file(file_path: str) -> List[Dict]:
    """Process file based on extension"""
    ext = Path(file_path).suffix.lower()

    if ext == '.csv':
        return load_csv(file_path)
    elif ext in ['.xlsx', '.xls']:
        return load_excel(file_path)
    elif ext == '.pdf':
        return load_pdf(file_path)
    else:
        logger.warning(f"Unsupported file type: {ext}")
        return []

def process_folder(folder_path: str, file_type: str = None) -> List[Dict]:
    """Process all files in folder"""
    documents = []

    path = Path(folder_path)
    if not path.exists():
        logger.error(f"Folder not found: {folder_path}")
        return documents

    # Define patterns based on file_type
    if file_type == 'csv':
        patterns = ['*.csv']
    elif file_type == 'excel':
        patterns = ['*.xlsx', '*.xls']
    elif file_type == 'pdf':
        patterns = ['*.pdf']
    else:
        patterns = ['*.csv', '*.xlsx', '*.xls', '*.pdf']

    for pattern in patterns:
        for file_path in path.glob(pattern):
            docs = process_file(str(file_path))
            documents.extend(docs)

    return documents

def main():
    parser = argparse.ArgumentParser(description='Knowledge Ingestion System')
    parser.add_argument('--csv', type=str, help='Path to CSV file')
    parser.add_argument('--excel', type=str, help='Path to Excel file')
    parser.add_argument('--url', type=str, help='Website URL to scrape')
    parser.add_argument('--pdf', type=str, help='Path to PDF file')
    parser.add_argument('--folder', type=str, help='Folder containing files')
    parser.add_argument('--type', type=str, choices=['csv', 'excel', 'pdf'],
                        help='File type for folder processing')
    parser.add_argument('--selector', type=str, help='CSS selector for web scraping')
    parser.add_argument('--chunk', action='store_true', help='Split documents into chunks')
    parser.add_argument('--dry-run', action='store_true', help='Preview without uploading')

    args = parser.parse_args()

    # Initialize clients
    supabase_client = get_supabase_client()
    openai_client = get_openai_client()

    if not supabase_client or not openai_client:
        logger.error("Failed to initialize clients. Check your API keys.")
        sys.exit(1)

    documents = []

    # Process input sources
    if args.csv:
        documents.extend(load_csv(args.csv))

    if args.excel:
        documents.extend(load_excel(args.excel))

    if args.url:
        documents.extend(scrape_website(args.url, args.selector))

    if args.pdf:
        documents.extend(load_pdf(args.pdf))

    if args.folder:
        documents.extend(process_folder(args.folder, args.type))

    if not documents:
        logger.warning("No documents to process")
        sys.exit(0)

    # Split into chunks if requested
    if args.chunk:
        chunked_docs = []
        for doc in documents:
            chunks = split_text_into_chunks(doc['content'])
            for i, chunk in enumerate(chunks):
                chunked_doc = doc.copy()
                chunked_doc['content'] = chunk
                chunked_doc['title'] = f"{doc['title']} (Part {i+1})" if len(chunks) > 1 else doc['title']
                chunked_docs.append(chunked_doc)
        documents = chunked_docs
        logger.info(f"Split into {len(documents)} chunks")

    logger.info(f"\n{'='*50}")
    logger.info(f"Total documents to process: {len(documents)}")
    logger.info(f"{'='*50}\n")

    # Preview documents
    for i, doc in enumerate(documents[:5]):
        logger.info(f"[{i+1}] {doc['title'][:50]}...")
        logger.info(f"    Category: {doc['category']}")
        logger.info(f"    Content: {doc['content'][:100]}...")
        logger.info("")

    if len(documents) > 5:
        logger.info(f"... and {len(documents) - 5} more documents")

    if args.dry_run:
        logger.info("\n[DRY RUN] No documents uploaded")
        return

    # Upload to Supabase
    logger.info("\nUploading to Supabase...")
    uploaded = upload_to_supabase(documents, supabase_client, openai_client)

    logger.info(f"\n{'='*50}")
    logger.info(f"✓ Successfully uploaded {uploaded}/{len(documents)} documents")
    logger.info(f"{'='*50}")

if __name__ == "__main__":
    main()
