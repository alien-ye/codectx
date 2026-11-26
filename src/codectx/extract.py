from importlib import import_module

from .store import SymbolRecord

_SUPPORTED_LANGS = {"python", "java", "groovy"}


def _module(lang):
    if lang not in _SUPPORTED_LANGS:
        raise ValueError(f"Unsupported language: {lang}")
    return import_module(".languages." + lang, __package__)


def extract_symbols(source, path, lang):
    return _module(lang).extract(source, path)


def extract_refs(source, path, lang):
    return _module(lang).extract_refs(source, path)


def persist_symbols(store, symbols):
    return [store.add_symbol(s) for s in symbols]


def extract_and_persist(store, root, rel_path, lang, source=None):
    source = source if source is not None else (root / rel_path).read_text(errors="replace")
    store.clear_file_symbols(rel_path)
    result, refs = _module(lang).analyze(source, rel_path)
    store._manifest.pop("error:" + rel_path, None)
    if not result.parse_ok:
        store.set_meta("error:" + rel_path, result.error)
    if not result.symbols and not result.parse_ok:
        store.add_symbol(
            SymbolRecord(rel_path, "<parse-error>", "<parse-error>", "function", parse_ok=False)
        )
    persist_symbols(store, result.symbols)
    for r in refs:
        r.file_path = rel_path
        store.add_ref(r)
    return len(result.symbols)
