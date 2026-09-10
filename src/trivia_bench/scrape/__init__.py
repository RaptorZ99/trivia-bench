"""Collecte des questions depuis l'API Open Trivia Database."""

from trivia_bench.scrape.client import BlockedByNetworkError, OpenTDBClient, OpenTDBError
from trivia_bench.scrape.runner import scrape_all

__all__ = ["BlockedByNetworkError", "OpenTDBClient", "OpenTDBError", "scrape_all"]
