# bioos_mcp/tools/rerank_client.py
import requests, json
from typing import List, Dict, Any

class RerankClient:
    def __init__(self, api_url: str, timeout: int = 30):
        self.api_url, self.timeout = api_url, timeout
        self.headers = {"Content-Type": "application/json"}

    def rerank(self, query: str, texts: List[str], top_n: int | None = None) -> List[Dict[str, Any]]:
        payload = {"query": query, "texts": texts}
        try:
            resp = requests.post(self.api_url, json=payload, headers=self.headers, timeout=self.timeout)
            resp.raise_for_status()
            scores = resp.json()            # [{index,score}, ...]
            ranked = sorted(
                [{"index": it["index"], "score": it["score"], "text": texts[it["index"]]} for it in scores],
                key=lambda x: x["score"], reverse=True
            )
            return ranked[:top_n] if top_n else ranked
        except (requests.RequestException, json.JSONDecodeError) as e:
            raise RuntimeError(f"Rerank API 调用失败: {e}")
