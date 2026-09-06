import os


def get_secret(secret_name: str) -> str | None:
    """
    Unified secret retrieval.

    Secrets come from environment variables only. Local development loads
    them from .env via load_dotenv() at the entrypoints (Home.py,
    admin_app.py); Cloud Run injects them as service env vars.
    """
    return os.environ.get(secret_name)
