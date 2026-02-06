"""
Phase 5.0: Knowledge Base - Document Processor
Handles document parsing, text extraction, and chunking for knowledge base.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Process documents and extract text content with chunking."""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 100):
        """
        Initialize document processor.

        Args:
            chunk_size: Maximum characters per chunk
            chunk_overlap: Character overlap between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def extract_text(self, file_path: str, document_type: str) -> str:
        """
        Extract text from document based on type.

        Args:
            file_path: Path to document file
            document_type: Type of document (txt, csv, json, pdf, docx)

        Returns:
            Extracted text content
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            if document_type == "txt":
                return self._extract_txt(path)
            elif document_type == "csv":
                return self._extract_csv(path)
            elif document_type == "json":
                return self._extract_json(path)
            elif document_type == "pdf":
                return self._extract_pdf(path)
            elif document_type == "docx":
                return self._extract_docx(path)
            else:
                raise ValueError(f"Unsupported document type: {document_type}")
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            raise

    def _extract_txt(self, path: Path) -> str:
        """Extract text from TXT file."""
        try:
            return path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            # Fallback to latin-1 if utf-8 fails
            return path.read_text(encoding='latin-1')

    def _extract_csv(self, path: Path) -> str:
        """Extract text from CSV file."""
        import csv

        lines = []
        with open(path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)

            # Add header
            if reader.fieldnames:
                lines.append("Column Headers: " + ", ".join(reader.fieldnames))
                lines.append("")

            # Add rows
            for i, row in enumerate(reader, 1):
                row_text = f"Row {i}:\n"
                for key, value in row.items():
                    row_text += f"  {key}: {value}\n"
                lines.append(row_text)

        return "\n".join(lines)

    def _extract_json(self, path: Path) -> str:
        """Extract text from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Pretty print JSON with indentation
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _extract_pdf(self, path: Path) -> str:
        """Extract text from PDF file."""
        try:
            import pdfplumber
        except ImportError:
            raise ImportError("pdfplumber is required for PDF support. Install with: pip install pdfplumber")

        text = []
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    text.append(f"[Page {page_num}]\n{page_text}")

        return "\n\n".join(text)

    def _extract_docx(self, path: Path) -> str:
        """Extract text from DOCX file."""
        try:
            from docx import Document
        except ImportError:
            raise ImportError("python-docx is required for DOCX support. Install with: pip install python-docx")

        doc = Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)

    def chunk_text(self, text: str) -> List[Dict[str, any]]:
        """
        Split text into overlapping chunks.

        Args:
            text: Full text content

        Returns:
            List of chunks with metadata
        """
        if not text or len(text) == 0:
            return []

        chunks = []
        start = 0
        chunk_index = 0

        while start < len(text):
            # Calculate end position
            end = start + self.chunk_size

            # If not the last chunk, try to break at sentence or word boundary
            if end < len(text):
                # Look for sentence boundary (. ! ?)
                sentence_end = max(
                    text.rfind('. ', start, end),
                    text.rfind('! ', start, end),
                    text.rfind('? ', start, end)
                )

                if sentence_end > start:
                    end = sentence_end + 1
                else:
                    # Look for word boundary (space)
                    space_pos = text.rfind(' ', start, end)
                    if space_pos > start:
                        end = space_pos

            # Extract chunk
            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append({
                    "chunk_index": chunk_index,
                    "content": chunk_text,
                    "char_count": len(chunk_text),
                    "start_pos": start,
                    "end_pos": end
                })
                chunk_index += 1

            # Move start position (with overlap)
            next_start = end - self.chunk_overlap

            # Prevent infinite loop: ensure we always move forward
            if next_start <= start:
                next_start = end

            start = next_start

            # Safety check: if we're not making progress, break
            if start >= len(text) and chunk_index > 0:
                break

        logger.info(f"Created {len(chunks)} chunks from {len(text)} characters")
        return chunks

    def process_document(self, file_path: str, document_type: str) -> List[Dict[str, any]]:
        """
        Process document: extract text and create chunks.

        Args:
            file_path: Path to document
            document_type: Type of document

        Returns:
            List of text chunks with metadata
        """
        logger.info(f"Processing document: {file_path} (type: {document_type})")

        # Extract text
        text = self.extract_text(file_path, document_type)
        logger.info(f"Extracted {len(text)} characters")

        # Create chunks
        chunks = self.chunk_text(text)
        logger.info(f"Created {len(chunks)} chunks")

        return chunks
