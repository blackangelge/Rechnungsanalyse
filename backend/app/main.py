"""
FastAPI-Anwendungsinstanz und Router-Registrierung.

Alle API-Endpunkte werden hier zentral registriert.
Die CORS-Middleware erlaubt Anfragen vom Next.js-Frontend.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import ai_configs, documents, items, logs, settings, sse
from app.routers import imports as imports_router  # 'imports' ist ein Python-Keyword

# ── FastAPI-Instanz ─────────────────────────────────────────────────────────
app = FastAPI(
    title="Rechnungsanalyse API",
    version="0.2.0",
    docs_url="/docs",    # Swagger UI
    redoc_url="/redoc",  # ReDoc UI
    redirect_slashes=False,
)

# ── CORS-Middleware ─────────────────────────────────────────────────────────
# Erlaubt Anfragen vom Frontend (konfigurierbar über BACKEND_CORS_ORIGINS in .env)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Router registrieren ─────────────────────────────────────────────────────
# Bestehende Router
app.include_router(items.router)           # /api/items/*

# Neue Router für das Rechnungsanalyse-System
app.include_router(ai_configs.router)      # /api/ai-configs/*
app.include_router(imports_router.router)  # /api/imports/* (POST, GET)
app.include_router(sse.router)             # /api/imports/{id}/progress (SSE)
app.include_router(documents.router)       # /api/documents/*
app.include_router(settings.router)        # /api/settings/*
app.include_router(logs.router)            # /api/logs/*


# ── Health-Check ────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health():
    """Einfacher Health-Check-Endpunkt für Docker-Healthchecks und Monitoring."""
    return {"status": "ok", "version": "0.2.0"}
