from dataclasses import dataclass

from .bm25 import BM25Index
from .tokens import query_tokens, split_identifier, tokenize


@dataclass(frozen=True, slots=True)
class LexHit:
    symbol_id: int
    score: float
    matched_terms: list[str]


def build_symbol_doc(sym):
    names = split_identifier(sym.name)
    doc = names * (4 if sym.kind == "class" else 2)
    for segment in sym.qualified_name.split("."):
        if segment != sym.name:
            doc.extend(split_identifier(segment))
    doc.extend(t.lower() for t in tokenize(sym.signature or ""))
    doc.extend(t.lower() for t in tokenize(sym.docstring or ""))
    return doc


class LexicalSearcher:
    """Reusable BM25; CLI cold cost includes constructing it."""

    def __init__(self, store, include_errors=False):
        self.symbols = [s for s in store.all_symbols() if s.parse_ok or include_errors]
        self.index = BM25Index.build(build_symbol_doc(s) for s in self.symbols)

    def search(self, query, k=10):
        terms = query_tokens(query)
        return [
            LexHit(
                self.symbols[i].id,
                score,
                sorted(set(terms) & set(build_symbol_doc(self.symbols[i]))),
            )
            for i, score in self.index.search(terms, k)
        ]


def search_lexical(store, query, k=10, include_errors=False):
    return LexicalSearcher(store, include_errors).search(query, k)
