from dotenv import load_dotenv

# Native runs read the repository's .env, found by walking up from this package. Containers get their
# environment from compose and ship no .env. Real environment variables always take precedence.
load_dotenv()
