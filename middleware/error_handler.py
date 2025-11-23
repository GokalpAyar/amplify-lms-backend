# middleware/error_handler.py
import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
import traceback

logger = logging.getLogger(__name__)

async def catch_exceptions_middleware(request: Request, call_next):
    """
    Global exception handler that catches all unhandled exceptions
    and returns a generic error response without exposing stack traces.
    """
    try:
        response = await call_next(request)
        return response
    except HTTPException:
        # Let FastAPI handle expected HTTP exceptions
        raise
    except Exception as e:
        # Log the full error with traceback for debugging
        logger.error(
            f"Unhandled exception: {str(e)}\n"
            f"URL: {request.url}\n"
            f"Method: {request.method}\n"
            f"Traceback: {traceback.format_exc()}"
        )
        
        # Return generic error response
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "type": "internal_error"
            }
        )