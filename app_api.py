# app_api.py
import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from db import init_db
from routes import assignments, responses, speech, users
from middleware.error_handler import catch_exceptions_middleware

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Amplify-LMS API",
    description="AI-Powered Learning Management System",
    version="1.0.0"
)

# --------------------------------------------------
# Global Exception Handler
# --------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception handler caught: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "type": "internal_error"
        }
    )

# --------------------------------------------------
# CORS settings (allow frontend to talk to backend)
# --------------------------------------------------
# Get origins from environment variable (comma-separated)
origins_env = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173")
origins = [origin.strip() for origin in origins_env.split(",")]

# Add common development and production origins
default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://localhost:5173",
]

# Combine environment origins with defaults, remove duplicates
all_origins = list(set(origins + default_origins))

logger.info(f"🛡️ CORS allowed origins: {all_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=all_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 🆕 ADD ERROR HANDLING MIDDLEWARE HERE
app.middleware("http")(catch_exceptions_middleware)

# --------------------------------------------------
# Health Check Endpoint
# --------------------------------------------------
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Amplify-LMS API",
        "version": "1.0.0"
    }

# --------------------------------------------------
# Register all routes
# --------------------------------------------------
app.include_router(users.router)        # ✅ signup/login endpoints
app.include_router(assignments.router)  # ✅ assignments CRUD
app.include_router(responses.router)    # ✅ student submissions
app.include_router(speech.router)       # ✅ audio upload / transcription

# --------------------------------------------------
# Initialize database on startup
# --------------------------------------------------
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Starting Amplify-LMS API...")
    logger.info(f"📁 Environment: {os.getenv('ENVIRONMENT', 'development')}")
    
    # Initialize database
    try:
        init_db()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise
    
    logger.info("✅ Amplify-LMS API started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Amplify-LMS API shutting down...")

# --------------------------------------------------
# Root endpoint
# --------------------------------------------------
@app.get("/")
async def root():
    return {
        "message": "Amplify-LMS API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }