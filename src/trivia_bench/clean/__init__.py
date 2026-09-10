"""Nettoyage et normalisation : couche bronze vers couche silver."""

from trivia_bench.clean.normalize import normalize_answer, strip_accents
from trivia_bench.clean.shuffle import shuffle_options

__all__ = ["normalize_answer", "shuffle_options", "strip_accents"]
