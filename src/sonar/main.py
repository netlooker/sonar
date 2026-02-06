"""Sonar - Standalone Strategic Discovery Service."""

import uvicorn
import logging
import os
from fastapi import FastAPI, HTTPException
from pathlib import Path
from pydantic import BaseModel
from .engine import SonarEngine, IntelBrief

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sonar")

app = FastAPI(title="Sonar Discovery Service")

# Singleton engine
engine = SonarEngine()

# Auth
AUTH_TOKEN = os.environ.get("SONAR_API_TOKEN", "sonar_internal")

class ResearchRequest(BaseModel):
    query: str
    token: str

@app.get("/health")
async def health_check():
    status = "online" if os.environ.get("TAVILY_API_KEY") else "degraded (no api key)"
    return {"service": "sonar", "status": status, "version": "1.0.0"}

@app.post("/research")
async def perform_research(request: ResearchRequest) -> IntelBrief:
    """Execute an agentic web research cycle."""
    if request.token != AUTH_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    logger.info(f"🛰️ [Sonar-Service] Researching: {request.query}")
    return await engine.research(request.query)

def start():
    """Entry point for the Sonar service."""
    # Port 8001 to avoid conflict with Echo (8000)
    port = int(os.environ.get("SONAR_PORT", 8001))
    
    # SSL Configuration (following Vessel Protocol)
    home = Path.home()
    cert_file = home / "netbox.tail839ce7.ts.net.crt"
    key_file = home / "netbox.tail839ce7.ts.net.key"
    
    ssl_config = {}
    if cert_file.exists() and key_file.exists():
        logger.info("🔐 SSL Enabled for Sonar.")
        ssl_config = {
            "ssl_keyfile": str(key_file),
            "ssl_certfile": str(cert_file)
        }
    else:
        logger.warning("⚠️ SSL Disabled for Sonar.")

    uvicorn.run("sonar.main:app", host="0.0.0.0", port=port, reload=False, **ssl_config)

if __name__ == "__main__":
    start()
