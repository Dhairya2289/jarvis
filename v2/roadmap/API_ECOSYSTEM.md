# API ECOSYSTEM: Redundancy & Power

## Free LLM APIs (The Swarm)

| Provider | Free Limit | Best Models | Speed | Primary Use |
| :--- | :--- | :--- | :--- | :--- |
| **Groq** | 14,400 req/day | Llama 3.3-70B, R1 | ⚡ 500+ tok/s | Speed Tier / Code |
| **Cerebras** | 25,000 req/day | Llama 3.3-70B | ⚡ 2000+ tok/s | Speed Tier |
| **SambaNova** | Generous | Llama 3.1-405B | Fast | Logic Tier / Research |
| **Google AI Studio** | 1M tok/day | Gemini 2.0 Flash | Fast | Vision / Default |
| **OpenRouter** | Free Pool | DeepSeek-R1, V3 | Medium | Logic / Fallback |
| **GitHub Models** | ~150 req/day | GPT-4o, Phi-4 | Medium | Code / Logic |
| **NVIDIA NIM** | Free Tier | Nemotron-120B | Medium | Complex Reasoning |
| **Ollama** | ∞ (Local) | Qwen 2.5, Phi-4 | GPU Speed | Infinite Fallback |

## Specialized Tool & Search APIs

| API | Free Limit | Use Case | Implementation |
| :--- | :--- | :--- | :--- |
| **Jina Reader** | Unlimited | URL → Markdown | `r.jina.ai/{url}` |
| **Serper** | 2,500/mo | Google SERP data | Web Research |
| **Tavily** | 1,000/mo | AI-native search | High-IQ Research |
| **DuckDuckGo** | Unlimited | No-key search | General Fallback |
| **OpenAlex** | 100K/day | 250M Academic papers | Science/History |
| **PubMed** | Generous | Biomedical research | Medical Literature |
| **arXiv** | Generous | CS/Physics preprints | Latest Tech |
| **Wolfram Alpha** | 2,000/mo | Math/Computation | Fact-checking |
| **yfinance** | Unlimited | Market Data | Stocks/Crypto |
| **Open-Meteo** | Unlimited | Weather | Environmental |

## Architecture: Smart API Rotation Manager

Goal: A single file (`api_manager.py`) that manages all providers, tracks quotas in real-time, rotates automatically on 429s, and caches responses.

### Key Logic (Draft)
```python
# api_manager.py (Planned)
class Provider:
    name: str
    base_url: str
    api_key_env: str
    rpm_limit: int
    best_for: list # ["speed", "logic", etc.]

# Smart Router
TASK_PROVIDER_MAP = {
    "speed":    ["groq", "cerebras", "ollama"],
    "logic":    ["openrouter", "sambanova", "fcc_proxy"],
    "research": ["gemini", "openalex", "pubmed"],
    "vision":   ["gemini", "github_models"]
}

def call_with_rotation(task, task_type, messages, system):
    # 1. Check local SQLite cache
    # 2. Get next available provider for task_type
    # 3. Try call; if 429, mark exhausted and recurse
```

## Integration Snippets

### 1. Jina Reader (Replacement for Scraper)
```python
def execute_jina_read(url: str) -> str:
    import requests
    r = requests.get(f"https://r.jina.ai/{url}", headers={"Accept": "text/plain"}, timeout=15)
    return r.text[:6000]
```

### 2. Tavily Search
```python
def execute_tavily_search(query: str, depth: str = "basic") -> str:
    import os, requests
    r = requests.post("https://api.tavily.com/search", json={
        "api_key": os.environ["TAVILY_API_KEY"],
        "query": query,
        "search_depth": depth,
        "include_answer": True,
        "max_results": 5
    }, timeout=15)
    data = r.json()
    return f"{data.get('answer', '')}\n\nSources:\n" + "\n".join(f"- {r['url']}" for r in data.get("results", []))
```
