import math
from array import array
from collections import Counter, defaultdict

K1, B = 1.5, 0.75


class BM25Index:
    def __init__(self):
        self.postings = defaultdict(lambda: array("I"))
        self.doc_len = []
        self.avgdl = 0
        self.n_docs = 0

    @classmethod
    def build(cls, docs):
        index = cls()
        for i, doc in enumerate(docs):
            index.doc_len.append(len(doc))
            for term, tf in Counter(doc).items():
                index.postings[term].extend((i, tf))
        index.n_docs = len(index.doc_len)
        index.avgdl = sum(index.doc_len) / max(1, index.n_docs)
        return index

    def idf(self, term):
        df = len(self.postings.get(term, ())) // 2
        return math.log(1 + (self.n_docs - df + 0.5) / (df + 0.5)) if df else 0

    def search(self, terms, k=10):
        if k <= 0:
            return []
        scores = defaultdict(float)
        for term in terms:
            idf = self.idf(term)
            postings = self.postings.get(term, array("I"))
            for i, tf in zip(postings[::2], postings[1::2], strict=True):
                denom = tf + K1 * (1 - B + B * self.doc_len[i] / (self.avgdl or 1))
                scores[i] += idf * tf * (K1 + 1) / denom
        return sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:k]
