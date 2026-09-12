"""
PDF Storage Abstraction Layer

This module provides a unified interface for storing and retrieving PDF files,
supporting local filesystem and Google Cloud Storage backends.

The abstraction allows the same code to work in both local development and
production Cloud Run environments.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Tuple
from io import BytesIO
import logging
import os


class PDFStorageBackend(ABC):
    """Abstract base class for PDF storage backends."""
    
    @abstractmethod
    def save_pdf(self, simulation_hash: str, pdf_buffer: BytesIO) -> str:
        """
        Save a PDF to storage.
        
        Args:
            simulation_hash: Unique identifier for the simulation
            pdf_buffer: BytesIO buffer containing the PDF data
            
        Returns:
            Storage path/identifier (e.g., file path or stage path)
        """
        pass
    
    @abstractmethod
    def get_pdf(self, storage_path: str) -> Optional[bytes]:
        """
        Retrieve a PDF from storage.
        
        Args:
            storage_path: Path/identifier returned by save_pdf
            
        Returns:
            PDF bytes, or None if not found
        """
        pass
    
    @abstractmethod
    def delete_pdf(self, storage_path: str) -> bool:
        """
        Delete a PDF from storage.
        
        Args:
            storage_path: Path/identifier to delete
            
        Returns:
            True if deleted, False if not found
        """
        pass
    
    @abstractmethod
    def get_download_info(self, storage_path: str) -> Tuple[str, Optional[bytes]]:
        """
        Get information needed for downloading the PDF.
        
        Args:
            storage_path: Path/identifier of the PDF
            
        Returns:
            Tuple of (download_type, data) where:
            - download_type: 'file' for direct bytes, 'url' for pre-signed URL
            - data: PDF bytes if type='file', URL string if type='url'
        """
        pass


class LocalFileStorageBackend(PDFStorageBackend):
    """
    Local filesystem storage backend for SQLite environments.
    Stores PDFs in a local directory structure.
    """
    
    def __init__(self, base_dir: str = "./pdf_cache"):
        """
        Initialize local file storage.
        
        Args:
            base_dir: Base directory for PDF storage
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logging.info(f"Initialized local PDF storage at: {self.base_dir.absolute()}")
    
    def _get_pdf_path(self, simulation_hash: str) -> Path:
        """
        Get the file path for a simulation's PDF.
        Uses sharding based on hash prefix for better filesystem performance.
        
        Example: abc123def... -> pdf_cache/ab/c1/abc123def.pdf
        """
        # Shard by first 4 characters for better filesystem performance
        shard1 = simulation_hash[:2]
        shard2 = simulation_hash[2:4]
        shard_dir = self.base_dir / shard1 / shard2
        shard_dir.mkdir(parents=True, exist_ok=True)
        return shard_dir / f"{simulation_hash}.pdf"
    
    def save_pdf(self, simulation_hash: str, pdf_buffer: BytesIO) -> str:
        """Save PDF to local filesystem."""
        pdf_path = self._get_pdf_path(simulation_hash)
        
        with open(pdf_path, 'wb') as f:
            f.write(pdf_buffer.getvalue())
        
        logging.info(f"Saved PDF to local file: {pdf_path}")
        return str(pdf_path)
    
    def get_pdf(self, storage_path: str) -> Optional[bytes]:
        """Retrieve PDF from local filesystem."""
        try:
            with open(storage_path, 'rb') as f:
                return f.read()
        except FileNotFoundError:
            logging.warning(f"PDF not found at path: {storage_path}")
            return None
    
    def delete_pdf(self, storage_path: str) -> bool:
        """Delete PDF from local filesystem."""
        try:
            Path(storage_path).unlink()
            logging.info(f"Deleted PDF: {storage_path}")
            return True
        except FileNotFoundError:
            return False
    
    def get_download_info(self, storage_path: str) -> Tuple[str, Optional[bytes]]:
        """Get PDF bytes for direct download."""
        pdf_bytes = self.get_pdf(storage_path)
        return ('file', pdf_bytes)


class GCSStorageBackend(PDFStorageBackend):
    """
    Google Cloud Storage backend for Cloud Run environment.
    Stores PDFs in a GCS bucket.
    """
    
    def __init__(self, bucket_name: str):
        from google.cloud import storage
        self.bucket_name = bucket_name
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)
        logging.info(f"Initialized GCS PDF storage with bucket: {bucket_name}")

    def save_pdf(self, simulation_hash: str, pdf_buffer: BytesIO) -> str:
        blob_name = f"{simulation_hash}.pdf"
        blob = self.bucket.blob(blob_name)
        
        # Rewind buffer just in case
        pdf_buffer.seek(0)
        blob.upload_from_file(pdf_buffer, content_type='application/pdf')
        
        logging.info(f"Saved PDF to GCS: gs://{self.bucket_name}/{blob_name}")
        return blob_name

    def get_pdf(self, storage_path: str) -> Optional[bytes]:
        try:
            blob = self.bucket.blob(storage_path)
            if not blob.exists():
                return None
            return blob.download_as_bytes()
        except Exception as e:
            logging.error(f"Failed to retrieve PDF from GCS: {e}")
            return None

    def delete_pdf(self, storage_path: str) -> bool:
        try:
            blob = self.bucket.blob(storage_path)
            if not blob.exists():
                return False
            blob.delete()
            logging.info(f"Deleted PDF from GCS: {storage_path}")
            return True
        except Exception as e:
            logging.error(f"Failed to delete PDF from GCS: {e}")
            return False

    def get_download_info(self, storage_path: str) -> Tuple[str, Optional[bytes]]:
        # Return file bytes for direct download via Streamlit
        return ('file', self.get_pdf(storage_path))


# Module-level cache for storage backend (singleton pattern)
_storage_backend_cache: Optional[PDFStorageBackend] = None


# Factory function to get the appropriate storage backend
def get_pdf_storage() -> PDFStorageBackend:
    """
    Get the appropriate PDF storage backend based on the environment.
    Uses module-level caching to avoid recreating the backend on every call.
    
    Returns:
        PDFStorageBackend instance (either LocalFileStorageBackend or GCSStorageBackend)
    """
    global _storage_backend_cache

    # Return cached instance if available
    if _storage_backend_cache is not None:
        return _storage_backend_cache

    # Check for GCS configuration. When GCS is explicitly configured, a
    # failure to initialize it must be fatal — falling back to local disk
    # would record container-local paths as pdf_status='ready' rows that no
    # other service can read (and the fallback would be cached for the
    # process lifetime).
    if os.getenv('PDF_STORAGE_BACKEND') == 'gcs':
        bucket_name = os.getenv('GCS_BUCKET_NAME')
        if not bucket_name:
            raise RuntimeError("PDF_STORAGE_BACKEND=gcs but GCS_BUCKET_NAME not set")
        logging.info(f"Using GCS storage backend with bucket: {bucket_name}")
        _storage_backend_cache = GCSStorageBackend(bucket_name)
        return _storage_backend_cache
    
    # Default to local file storage
    logging.info("Using local file storage backend")
    _storage_backend_cache = LocalFileStorageBackend()
    return _storage_backend_cache

