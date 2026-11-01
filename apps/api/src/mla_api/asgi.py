"""ASGI entry point: uvicorn mla_api.asgi:app --reload (run from apps/api with PYTHONPATH=src)."""
import logging

from mla_api.main import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
