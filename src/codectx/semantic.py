import os
from dataclasses import dataclass
from functools import lru_cache

DEFAULT_MODEL_NAME = "minishlab/potion-code-16M-v2"


def _env_model_name():
    return os.environ.get("CODECTX_MODEL_NAME", DEFAULT_MODEL_NAME)


def _compose_doc(sym):
    return "\n".join(
        str(x)
        for x in (
            sym.name,
            sym.name,
            sym.qualified_name if sym.qualified_name != sym.name else None,
            sym.signature,
            sym.docstring,
        )
        if x
    )


@lru_cache(maxsize=2)
def _load_model(name):
    from model2vec import StaticModel

    return StaticModel.from_pretrained(name)


@dataclass(frozen=True, slots=True)
class SemanticHit:
    symbol_id: int
    score: float


def embed_symbols(store, symbols, model_name=None):
    import numpy as np

    name = model_name or _env_model_name()
    model = _load_model(name)
    directory = store.index_dir / "vectors"
    directory.mkdir(parents=True, exist_ok=True)
    work = directory / ".embedding-work.npy"
    if symbols:
        matrix = np.lib.format.open_memmap(
            work, mode="w+", dtype=np.float32, shape=(len(symbols), model.dim)
        )
        for start in range(0, len(symbols), 1024):
            batch = symbols[start : start + 1024]
            matrix[start : start + len(batch)] = model.encode(
                [_compose_doc(s) for s in batch], use_multiprocessing=False
            )
        matrix.flush()
    else:
        matrix = np.zeros((0, model.dim), dtype=np.float32)
    try:
        store.set_vectors([s.id for s in symbols], matrix, name)
    finally:
        del matrix
        work.unlink(missing_ok=True)
    store.set_meta("vector_fingerprint", store.fingerprint())
    return len(symbols)


class SemanticSearcher:
    def __init__(self, store, model_name=None):
        import numpy as np

        self.ids, self.matrix, self.model = [], None, None
        vectors = store.get_vectors()
        if vectors is None:
            return
        self.ids, matrix, stored_name = vectors
        name = model_name or _env_model_name()
        if stored_name != name:
            raise RuntimeError(f"Stored model {stored_name} differs from {name}; run embed --force")
        self.model = _load_model(name)
        self.matrix = matrix
        self.norms = np.empty(len(matrix), dtype=np.float32)
        for start in range(0, len(matrix), 8192):
            self.norms[start : start + 8192] = np.maximum(
                np.linalg.norm(matrix[start : start + 8192], axis=1), 1e-12
            )

    def search(self, query, k=10):
        import numpy as np

        if self.matrix is None or k <= 0:
            return []
        vec = self.model.encode([query], use_multiprocessing=False)[0]
        norm = np.linalg.norm(vec)
        if norm == 0:
            return []
        scores = (self.matrix @ (vec / norm)) / self.norms
        k = min(k, len(scores))
        indices = np.argpartition(-scores, k - 1)[:k]
        return [
            SemanticHit(self.ids[i], float(scores[i]))
            for i in sorted(indices, key=lambda i: (-scores[i], i))
        ]


def search_semantic(store, query, k=10, model_name=None):
    return SemanticSearcher(store, model_name).search(query, k)
