"""Evaluation metrics: CER, WER and field-level precision/recall/F1.

Corpus-level CER/WER are computed as total edits / total reference length (not the mean
of per-document rates), which is the standard and avoids short documents dominating.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


def levenshtein(a: Sequence[Any], b: Sequence[Any]) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def normalize_text(text: str, *, casefold: bool = False) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold() if casefold else text


@dataclass(frozen=True)
class ErrorRate:
    edits: int
    ref_len: int

    @property
    def rate(self) -> float:
        if self.ref_len == 0:
            return 0.0 if self.edits == 0 else 1.0
        return self.edits / self.ref_len


def cer(reference: str, hypothesis: str, *, casefold: bool = False) -> ErrorRate:
    ref = normalize_text(reference, casefold=casefold)
    hyp = normalize_text(hypothesis, casefold=casefold)
    return ErrorRate(levenshtein(ref, hyp), len(ref))


def wer(reference: str, hypothesis: str, *, casefold: bool = False) -> ErrorRate:
    ref = normalize_text(reference, casefold=casefold).split()
    hyp = normalize_text(hypothesis, casefold=casefold).split()
    return ErrorRate(levenshtein(ref, hyp), len(ref))


def corpus_rate(
    refs: Sequence[str],
    hyps: Sequence[str],
    fn: Callable[..., ErrorRate],
    *,
    casefold: bool = False,
) -> ErrorRate:
    if len(refs) != len(hyps):
        raise ValueError("refs and hyps must have the same length")
    edits = ref_len = 0
    for r, h in zip(refs, hyps, strict=True):
        er = fn(r, h, casefold=casefold)
        edits += er.edits
        ref_len += er.ref_len
    return ErrorRate(edits, ref_len)


# --------------------------------------------------------------------------- field F1


def _norm_field(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    s = normalize_text(str(value), casefold=True)
    return s or None


@dataclass
class PRF:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


@dataclass
class FieldReport:
    per_field: dict[str, PRF] = field(default_factory=dict)

    @property
    def micro(self) -> PRF:
        total = PRF()
        for prf in self.per_field.values():
            total.tp += prf.tp
            total.fp += prf.fp
            total.fn += prf.fn
        return total

    def as_dict(self) -> dict[str, Any]:
        return {
            "per_field": {k: v.as_dict() for k, v in self.per_field.items()},
            "micro": self.micro.as_dict(),
        }


def field_prf(
    gold: Sequence[Mapping[str, Any]],
    pred: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
    normalizer: Callable[[Any], str | None] = _norm_field,
) -> FieldReport:
    """Exact-match (after normalization) field-level P/R/F1.

    * gold set, pred equal      -> TP
    * gold set, pred different  -> FP + FN (a wrong value is both)
    * gold set, pred missing    -> FN
    * gold missing, pred set    -> FP
    """
    if len(gold) != len(pred):
        raise ValueError("gold and pred must have the same length")
    report = FieldReport({f: PRF() for f in fields})
    for g, p in zip(gold, pred, strict=True):
        for f in fields:
            gv, pv = normalizer(g.get(f)), normalizer(p.get(f))
            prf = report.per_field[f]
            if gv is not None and pv is not None:
                if gv == pv:
                    prf.tp += 1
                else:
                    prf.fp += 1
                    prf.fn += 1
            elif gv is not None:
                prf.fn += 1
            elif pv is not None:
                prf.fp += 1
    return report
