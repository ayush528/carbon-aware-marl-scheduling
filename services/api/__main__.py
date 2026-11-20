"""``python -m services.api`` runs the service on :8000 (used by ``make api``)."""

from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run("services.api.main:app", host="127.0.0.1", port=8000, reload=False)
