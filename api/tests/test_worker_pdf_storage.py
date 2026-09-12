#!/usr/bin/env python3
"""
Worker PDF save path must go through the storage backend abstraction
(local pdf_cache/ in dev, GCS in prod) — never write the filesystem
directly, or PDFs land on an ephemeral disk the API can't see on Cloud Run.
"""

from io import BytesIO
from unittest.mock import Mock, patch


class TestWorkerPdfStorageBackend:

    def test_pdf_generation_saves_via_storage_backend(self):
        from services.background_worker import JobWorker

        worker = JobWorker("test_worker")

        fake_cursor = Mock()
        fake_cursor.fetchone.return_value = ("ab" * 32,)
        fake_conn = Mock()

        fake_backend = Mock()
        fake_backend.save_pdf.return_value = "ab" * 32 + ".pdf"

        pdf_buffer = BytesIO(b"%PDF-1.4 fake")

        with patch("db.database.db") as fake_db, \
             patch("db.pdf_storage.get_pdf_storage", return_value=fake_backend) as fake_get_storage, \
             patch("background_tasks._generate_pdf_for_simulation", return_value=pdf_buffer):
            fake_db.get_connection.return_value = fake_conn
            fake_db._get_cursor.return_value = fake_cursor

            result = worker._process_pdf_generation("test-job-1", {"history_id": 42})

        simulation_hash = "ab" * 32
        fake_get_storage.assert_called_once()
        fake_backend.save_pdf.assert_called_once_with(simulation_hash, pdf_buffer)

        # The DB row must record the path the backend returned (a GCS blob
        # name in prod), not a locally-constructed filesystem path.
        kwargs = fake_db.update_simulation_pdf_storage.call_args.kwargs
        assert kwargs["storage_path"] == fake_backend.save_pdf.return_value
        assert kwargs["status"] == "ready"
        assert result["success"] is True
        assert result["pdf_path"] == fake_backend.save_pdf.return_value
