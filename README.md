# Sonar 📡

**Standalone Strategic Discovery Service for the Netlooker Empire.**

Sonar is a high-fidelity web discovery engine designed to act as the "Tactical Ear" for the Cyber Family. It transforms raw search queries into structured, high-signal intel briefs.

Built on **PydanticAI**, Sonar uses an autonomous research loop to ensure that every answer is grounded in real-time truth from the global internet.

---

## ✨ Features
- **Agentic Research**: Not just a keyword search. Sonar uses an internal LLM agent to plan, expand, and synthesize search results.
- **Tavily Integration**: Powered by the **Tavily AI Search API** using `advanced` search depth for maximum precision.
- **Structured Intel**: Returns **IntelBrief** models containing a dense summary and a curated list of sources.
- **Service Composition**: Designed to be called over the network by other vessels (e.g., Echo) following the **[[Vessel Protocol]]**.
- **Secure by Design**: Operates with mandatory token-based authentication and SSL.

---

## 🚀 Getting Started

### 1. Setup Environment
```bash
# In projects/vessel/.vessel_env (or local environment)
export TAVILY_API_KEY="tvly-xxx"
export SONAR_API_TOKEN="your_secure_internal_token"
```

### 2. Run the Service
```bash
cd sonar
./run.sh
```
The service will be active at `https://localhost:8001`.

---

## 🛠️ API Reference

### `GET /health`
Returns the status of the service and confirms if the Tavily API key is active.

### `POST /research`
Performs a full agentic research cycle.
**Request Body:**
```json
{
  "query": "Who won the 2025 F1 championship?",
  "token": "sonar_internal"
}
```

---

## 🔗 Connections
- [[Recon Suite]]
- [[Tavily]]
- [[Vessel Protocol]]
- [[Echo]]

---

*"Scanning the horizon for the signals that matter."* 🌑
