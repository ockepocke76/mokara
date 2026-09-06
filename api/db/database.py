from .factory import get_database

# Module-level singleton: Python's module cache guarantees one instance per
# process, which is exactly what the old st.cache_resource wrapper provided.
db = get_database()
