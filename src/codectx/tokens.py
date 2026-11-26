import re

_TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_STOPWORDS = set(
    [
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "am",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "in",
        "on",
        "at",
        "to",
        "from",
        "for",
        "of",
        "with",
        "by",
        "as",
        "into",
        "over",
        "under",
        "and",
        "or",
        "not",
        "but",
        "if",
        "then",
        "else",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "where",
        "when",
        "why",
        "how",
        "all",
        "any",
        "some",
        "no",
        "each",
        "every",
        "do",
        "does",
        "did",
        "doing",
        "has",
        "have",
        "had",
        "can",
        "could",
        "should",
        "would",
        "will",
        "shall",
        "may",
        "might",
        "must",
        "i",
        "me",
        "my",
        "mine",
        "we",
        "us",
        "our",
        "ours",
        "you",
        "your",
        "yours",
        "he",
        "him",
        "his",
        "she",
        "her",
        "hers",
        "it",
        "its",
        "they",
        "them",
        "their",
        "theirs",
    ]
)


def tokenize(text):
    return _TOKEN_RE.findall(text)


def split_identifier(ident):
    split = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", ident)
    split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", split)
    parts = split.replace("_", " ").lower().split()
    return list(dict.fromkeys([ident.lower(), *parts]))


def query_tokens(query):
    return [
        part
        for token in tokenize(query)
        for part in split_identifier(token)
        if part not in _STOPWORDS
    ]
