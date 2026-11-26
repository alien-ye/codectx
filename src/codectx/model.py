from dataclasses import dataclass, field

from .store import RefRecord, SymbolRecord

Symbol = SymbolRecord


@dataclass(slots=True)
class ExtractResult:
    symbols: list[Symbol] = field(default_factory=list)
    parse_ok: bool = True
    error: str | None = None


RawRef = RefRecord
