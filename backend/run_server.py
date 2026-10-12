import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.chdir(BACKEND_ROOT)
load_dotenv(BACKEND_ROOT.parent / ".env", override=False)

if __name__ == "__main__":
    import uvicorn

    is_render = bool(os.getenv("RENDER"))
    host = os.getenv("HOST", "0.0.0.0" if is_render else "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=not is_render)
