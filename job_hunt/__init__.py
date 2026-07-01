"""job_hunt package. Loading .env.local / .env here (before any submodule imports)
means DB_BACKEND, API_TOKEN, DATABASE_URL, etc. from those files take effect without
prefixing every command. Real shell exports still win; skipped under pytest."""
from job_hunt.env import load_env_files

load_env_files()
