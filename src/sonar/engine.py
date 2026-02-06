import os
import asyncio
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from dataclasses import dataclass
from tavily import TavilyClient

# Import Phantom Client
import sys
from pathlib import Path
phantom_src = Path(__file__).parent.parent.parent.parent / "phantom/backend/src"
if phantom_src.exists():
    sys.path.append(str(phantom_src))
    try:
        from phantom.client import log_recon_event
    except ImportError:
        async def log_recon_event(*args, **kwargs): pass
else:
    async def log_recon_event(*args, **kwargs): pass

# Setup logging
logger = logging.getLogger("sonar.agent")

@dataclass
class SonarDeps:
    """Dependencies for the Sonar Researcher."""
    tavily_key: str

class SearchResult(BaseModel):
    """A single search result."""
    title: str
    url: str
    content: str
    score: float

class IntelBrief(BaseModel):
    """Structured response from Sonar."""
    summary: str = Field(description="A concise summary of the gathered information")
    sources: List[SearchResult] = Field(description="The primary sources used for this brief")

# --- SONAR AGENT ---
sonar_agent = Agent(
    os.environ.get("SONAR_MODEL", "openai:glm-flash-64k:latest"),
    deps_type=SonarDeps,
    output_type=IntelBrief,
    system_prompt=(
        "You are Sonar, the Strategic Discovery Engine for the Netlooker Empire. "
        "Your mission is to perform high-fidelity web research via Tavily. 📡"
    )
)

@sonar_agent.tool
async def web_search(ctx: RunContext[SonarDeps], query: str) -> str:
    """
    Search the live web for real-time information via Tavily.
    """
    logger.info(f"📡 [Sonar-Ping] Query: {query}")
    search_url = f"https://tavily.com/search?q={query.replace(' ', '+')}"
    
    try:
        await log_recon_event("sonar", "web_search", search_url, "active")
        
        tavily = TavilyClient(api_key=ctx.deps.tavily_key)
        response = await asyncio.to_thread(
            tavily.search,
            query=query,
            search_depth="advanced",
            max_results=5,
            include_answer=True
        )
        
        results = response.get("results", [])
        output = f"Direct Answer: {response.get('answer', 'N/A')}\n\nSources:\n"
        for r in results:
            output += f"- {r['title']} ({r['url']}): {r['content']}\n"
        
        await log_recon_event("sonar", "web_search", search_url, "success", signal_strength=len(output), content=output)
        return output
    except Exception as e:
        await log_recon_event("sonar", "web_search", search_url, "error", content=str(e))
        return f"Search error: {str(e)}"

class SonarEngine:
    def __init__(self):
        self.tavily_key = os.environ.get("TAVILY_API_KEY")

    async def research(self, query: str) -> IntelBrief:
        if not self.tavily_key:
            return IntelBrief(summary="Error: No Tavily Key", sources=[])
        deps = SonarDeps(tavily_key=self.tavily_key)
        try:
            result = await sonar_agent.run(query, deps=deps)
            return result.output
        except Exception as e:
            return IntelBrief(summary=f"Error: {str(e)}", sources=[])
