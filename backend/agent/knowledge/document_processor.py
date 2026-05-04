"""
Phase 5.0: Knowledge Base - Document Processor
Handles document parsing, text extraction, and chunking for knowledge base.
"""

import json
import logging
import csv
from pathlib import Path
from typing import Any, List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Process documents and extract text content with chunking."""

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        chunk_strategy: str = "fixed_text",
    ):
        """
        Initialize document processor.

        Args:
            chunk_size: Maximum characters per chunk
            chunk_overlap: Character overlap between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.chunk_strategy = chunk_strategy or "fixed_text"

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

    def chunk_text(self, text: str) -> List[Dict[str, Any]]:
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
                    "end_pos": end,
                    "chunk_strategy": "fixed_text",
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

    def _chunk_json_structure(self, file_path: str) -> List[Dict[str, Any]]:
        path = Path(file_path)
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        rows: List[tuple[str, Any]] = []

        def walk(value: Any, json_path: str) -> None:
            if isinstance(value, dict):
                if not value:
                    rows.append((json_path, value))
                for key, child in value.items():
                    child_path = f"{json_path}.{key}" if json_path else str(key)
                    walk(child, child_path)
            elif isinstance(value, list):
                if not value:
                    rows.append((json_path, value))
                for index, child in enumerate(value):
                    walk(child, f"{json_path}[{index}]")
            else:
                rows.append((json_path or "$", value))

        walk(data, "$")
        chunks: List[Dict[str, Any]] = []
        for json_path, value in rows:
            rendered = f"{json_path}: {json.dumps(value, ensure_ascii=False)}"
            if len(rendered) <= self.chunk_size:
                chunks.append(
                    {
                        "chunk_index": len(chunks),
                        "content": rendered,
                        "char_count": len(rendered),
                        "start_pos": 0,
                        "end_pos": len(rendered),
                        "chunk_strategy": "json_structure",
                        "json_path": json_path,
                    }
                )
                continue

            for chunk in self.chunk_text(rendered):
                chunk["chunk_index"] = len(chunks)
                chunk["chunk_strategy"] = "json_structure"
                chunk["json_path"] = json_path
                chunks.append(chunk)

        logger.info("Created %d JSON-structure chunks", len(chunks))
        return chunks

    def _chunk_csv_rows(self, file_path: str) -> List[Dict[str, Any]]:
        path = Path(file_path)
        with open(path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            chunks: List[Dict[str, Any]] = []
            current_rows: List[str] = []
            current_start_row = 1

            def flush_rows(end_row: int) -> None:
                nonlocal current_rows, current_start_row
                if not current_rows:
                    return
                content = "Headers: " + ", ".join(headers) + "\n" + "\n".join(current_rows)
                chunks.append(
                    {
                        "chunk_index": len(chunks),
                        "content": content,
                        "char_count": len(content),
                        "start_pos": 0,
                        "end_pos": len(content),
                        "chunk_strategy": "csv_rows",
                        "row_start": current_start_row,
                        "row_end": end_row,
                    }
                )
                current_rows = []
                current_start_row = end_row + 1

            for row_number, row in enumerate(reader, 1):
                rendered = " | ".join(f"{header}: {row.get(header, '')}" for header in headers)
                projected = (
                    "Headers: " + ", ".join(headers) + "\n" + "\n".join(current_rows + [rendered])
                )
                if current_rows and len(projected) > self.chunk_size:
                    flush_rows(row_number - 1)
                if len(rendered) > self.chunk_size:
                    for chunk in self.chunk_text(rendered):
                        chunk["chunk_index"] = len(chunks)
                        chunk["chunk_strategy"] = "csv_rows"
                        chunk["row_start"] = row_number
                        chunk["row_end"] = row_number
                        chunks.append(chunk)
                    current_start_row = row_number + 1
                else:
                    if not current_rows:
                        current_start_row = row_number
                    current_rows.append(rendered)
            flush_rows(row_number if "row_number" in locals() else 0)

        logger.info("Created %d CSV-row chunks", len(chunks))
        return chunks

    def process_document(
        self,
        file_path: str,
        document_type: str,
        chunk_strategy: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Process document: extract text and create chunks.

        Args:
            file_path: Path to document
            document_type: Type of document

        Returns:
            List of text chunks with metadata
        """
        logger.info(f"Processing document: {file_path} (type: {document_type})")

        strategy = chunk_strategy or self.chunk_strategy or "fixed_text"

        if strategy == "json_structure" and document_type == "json":
            return self._chunk_json_structure(file_path)
        if strategy == "csv_rows" and document_type == "csv":
            return self._chunk_csv_rows(file_path)

        # Extract text
        text = self.extract_text(file_path, document_type)
        logger.info(f"Extracted {len(text)} characters")

        # Create chunks
        chunks = self.chunk_text(text)
        logger.info(f"Created {len(chunks)} chunks")

        return chunks
