import os
import asyncio
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from dataclasses import dataclass
from tavily import TavilyClient

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
    os.environ.get("SONAR_MODEL", "openai:glm-4.7-flash:latest"),
    deps_type=SonarDeps,
    output_type=IntelBrief,
    system_prompt=(
        "You are Sonar, the Strategic Discovery Engine for the Netlooker Empire. "
        "Your mission is to perform high-fidelity web research. "
        "You have access to the Tavily Search tool. "
        "Analyze the user's request, perform searches as needed, and synthesize a dense intel brief. "
        "Focus on truth, precision, and high-signal data. 📡"
    )
)

@sonar_agent.tool
async def web_search(ctx: RunContext[SonarDeps], query: str) -> str:
    """
    Search the live web for real-time information. 
    Use this for facts, news, documentation, or anything not in local memory.
    """
    logger.info(f"📡 [Sonar-Ping] Query: {query}")
    try:
        tavily = TavilyClient(api_key=ctx.deps.tavily_key)
        response = await asyncio.to_thread(
            tavily.search,
            query=query,
            search_depth="advanced",
            max_results=5,
            include_answer=True
        )
        
        # Format results for the LLM to process
        results = response.get("results", [])
        output = f"Direct Answer: {response.get('answer', 'N/A')}\n\nSources:\n"
        for r in results:
            output += f"- {r['title']} ({r['url']}): {r['content']}\n"
        
        return output
    except Exception as e:
        logger.error(f"❌ [Sonar-Ping] Error: {e}")
        return f"Search error: {str(e)}"

class SonarEngine:
    """The core engine interface for Sonar."""
    
    def __init__(self):
        self.tavily_key = os.environ.get("TAVILY_API_KEY")
        if not self.tavily_key:
            logger.warning("⚠️ TAVILY_API_KEY not found in environment.")

    async def research(self, query: str) -> IntelBrief:
        """Execute a full research cycle."""
        if not self.tavily_key:
            return IntelBrief(
                summary="Sonar Error: TAVILY_API_KEY not configured.",
                sources=[]
            )

        deps = SonarDeps(tavily_key=self.tavily_key)
        
        try:
            result = await sonar_agent.run(query, deps=deps)
            return result.output
        except Exception as e:
            logger.error(f"💀 [Sonar-Engine] Critical Failure: {e}")
            return IntelBrief(
                summary=f"Internal system error during research: {str(e)}",
                sources=[]
            )
