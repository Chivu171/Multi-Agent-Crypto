import threading
import json
import os
from typing import Dict, List, Any

class DebateBuffer:
    """Thread‑safe in‑memory buffer for debate evidence.
    Stores a mapping of agent_id -> list of evidence chunks (dicts).
    Optionally persists to a JSON file for later analysis.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._store: Dict[str, List[Dict[str, Any]]] = {}

    def publish(self, agent_id: str, chunk: Dict[str, Any]):
        """Add a new evidence chunk for the given agent."""
        with self._lock:
            self._store.setdefault(agent_id, []).append(chunk)

    def get(self, agent_id: str) -> Dict[str, Any]:
        """Return the most recent chunk stored for the given agent.
        If no data exists, returns an empty dict."""
        with self._lock:
            items = self._store.get(agent_id, [])
            return items[-1] if items else {}


    def get_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """Return a copy of the entire buffer content."""
        with self._lock:
            # shallow copy is enough for read‑only purposes
            return {k: list(v) for k, v in self._store.items()}

    def persist(self, filepath: str = "outputs/debate_history.json") -> None:
        """Write the current buffer to a JSON file.
        The directory is created if it does not exist.
        """
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self._store, f, ensure_ascii=False, indent=2)
