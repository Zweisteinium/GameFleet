"""Process-wide switches read from the environment (the root .env is loaded by the package __init__)."""
import os

# GAMEFLEET_ENV=dev is for working on GameFleet: API docs are served, logging is verbose and a dashboard
# without configured users is open to everyone. Anything else is production, where none of that holds.
DEV = os.getenv("GAMEFLEET_ENV", "prod").strip().lower() in ("dev", "development")
