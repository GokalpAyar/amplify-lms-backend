# app_api.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db import init_db
from routes import assignments, responses, speech

app = FastAPI(title="Amplify-LMS API")

origins = [
    os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assignments.router)
app.include_router(responses.router)
app.include_router(speech.router)

@app.on_event("startup")
def startup():
    init_db()
