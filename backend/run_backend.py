import os

import uvicorn


if __name__ == "__main__":
    port = int(os.getenv("BACKEND_PORT", "8010"))
    reload = os.getenv("BACKEND_RELOAD", "0").lower() in {"1", "true", "yes", "on"}
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=reload)
