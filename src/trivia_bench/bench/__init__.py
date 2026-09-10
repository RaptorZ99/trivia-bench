"""Interrogation du modele, notation des reponses et ecriture de la couche silver."""

from trivia_bench.bench.grading import GradeResult, grade_answer
from trivia_bench.bench.lmstudio import LMStudioClient, LMStudioError
from trivia_bench.bench.prompts import PROMPT_VARIANTS, PromptVariant, render_request

__all__ = [
    "PROMPT_VARIANTS",
    "GradeResult",
    "LMStudioClient",
    "LMStudioError",
    "PromptVariant",
    "grade_answer",
    "render_request",
]
