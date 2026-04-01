import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langserve import add_routes
from src.config import RUNTIME_REQUIRED_SETTINGS, validate_required_settings
from src.graph import Workflow

settings = validate_required_settings(RUNTIME_REQUIRED_SETTINGS)
app = FastAPI(
    title=settings.api.title,
    version=settings.api.version,
    description=settings.api.description,
)

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

def get_runnable():
    return  Workflow().app

# Fetch LangGraph Automation runnable which generates the workouts
runnable = get_runnable()

# Create the Fast API route to invoke the runnable
add_routes(app, runnable)

def main():
    # Start the API
    uvicorn.run(app, host=settings.api.host, port=settings.api.port)

if __name__ == "__main__":
    main()
