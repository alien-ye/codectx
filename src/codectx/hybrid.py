import math
import warnings
from dataclasses import dataclass

from .graph import subtypes
from .search import LexicalSearcher
from .semantic import SemanticSearcher

RRF_K = 60


@dataclass(frozen=True, slots=True)
class HybridHit:
    symbol_id: int
    score: float
    lexical_rank: int | None
    semantic_rank: int | None


class HybridSearcher:
    def __init__(self, store, lexical=None, semantic=None):
        self.store = store
        self.lexical = lexical or LexicalSearcher(store)
        self.degraded_reason = None
        try:
            self.semantic = semantic or SemanticSearcher(store)
        except RuntimeError as e:
            self.semantic = None
            self.degraded_reason = str(e)
            warnings.warn(f"Semantic search unavailable: {e}", stacklevel=2)
        self._boosts = {}

    def search(self, query, k=10, boost=None):
        if boost is None:
            name = query.strip()
            boost = name not in self.store.by_name and name not in self.store.by_qname
        fetch = max(3 * k, 30)
        lexical = {h.symbol_id: r for r, h in enumerate(self.lexical.search(query, fetch))}
        semantic = (
            {h.symbol_id: r for r, h in enumerate(self.semantic.search(query, fetch))}
            if self.semantic
            else {}
        )
        hits = []
        for sid in sorted(lexical.keys() | semantic.keys()):
            score = sum(
                1 / (RRF_K + ranks[sid] + 1) for ranks in (lexical, semantic) if sid in ranks
            )
            if boost:
                if sid not in self._boosts:
                    s = self.store.symbol_by_id(sid)
                    n = (
                        len({h.target.id for h in subtypes(self.store, sid, 1) if h.target})
                        if s.kind == "class"
                        else 0
                    )
                    self._boosts[sid] = math.log2(n + 1) if n else 1
                score *= self._boosts[sid]
            hits.append(HybridHit(sid, score, lexical.get(sid), semantic.get(sid)))
        return sorted(hits, key=lambda h: (-h.score, h.symbol_id))[:k]


def search_hybrid(store, query, k=10):
    return HybridSearcher(store).search(query, k)
