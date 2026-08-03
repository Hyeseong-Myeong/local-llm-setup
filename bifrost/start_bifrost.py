import os
import base64
import subprocess
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(env_path)

langfuse_public = os.getenv("LANGFUSE_PUBLIC_KEY", "")
langfuse_secret = os.getenv("LANGFUSE_SECRET_KEY", "")
langfuse_host = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

if not langfuse_public or not langfuse_secret:
    print("Error: LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY is missing in .env")
    exit(1)

# Generate Base64 Auth
auth_str = f"{langfuse_public}:{langfuse_secret}"
auth_b64 = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")

# Prepare environment for docker-compose
env = os.environ.copy()
env["LANGFUSE_AUTH_B64"] = auth_b64

print("Starting Bifrost Gateway via docker-compose...")
result = subprocess.run(["docker-compose", "up", "-d"], env=env, cwd=os.path.dirname(__file__))

if result.returncode == 0:
    print("Bifrost started successfully!")
else:
    print(f"Failed to start Bifrost. Exit code: {result.returncode}")
