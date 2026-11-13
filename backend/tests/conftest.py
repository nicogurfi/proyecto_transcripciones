import os
import sys
from pathlib import Path

# Tests deterministas, offline y rápidos: modo mock, sin red, embeddings por hashing.
os.environ["LLM_PROVIDER"] = "mock"
os.environ["USIG_ENABLED"] = "false"
os.environ["EMBEDDINGS_ENABLED"] = os.environ.get("TEST_EMBEDDINGS", "false")
os.environ["DB_PATH"] = str(Path(__file__).parent / ".test.db")
sys.path.insert(0, str(Path(__file__).parent.parent))
