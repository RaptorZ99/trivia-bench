"""Boucle de benchmark : une variante de prompt, un modele, toutes les questions.

L'execution est strictement sequentielle (une requete en vol a la fois) : le traitement par
lots du serveur fausserait les mesures de latence par question. Chaque reponse est ecrite dans
un fichier JSONL des sa reception, ce qui rend le run reprenable apres une interruption.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from trivia_bench.bench.dataset import fewshot_examples, load_questions, select_questions
from trivia_bench.bench.lmstudio import LMStudioClient
from trivia_bench.bench.manifest import build_manifest, load_manifest, save_manifest
from trivia_bench.bench.prompts import PROMPT_VARIANTS, render_request
from trivia_bench.bench.silver import grade_runs
from trivia_bench.config import Settings
from trivia_bench.logging import logger
from trivia_bench.models import Question, ReasoningMode, RunManifest
from trivia_bench.paths import DataPaths

WARMUP_QUESTION = Question(
    question_id="0" * 64,
    category_id=0,
    category="Warm-up",
    category_group="Warm-up",
    type="multiple",
    difficulty="easy",
    question="What is the capital of France?",
    correct_answer="Paris",
    incorrect_answers=["Lyon", "Marseille", "Toulouse"],
    options=["Lyon", "Paris", "Marseille", "Toulouse"],
    correct_index=1,
    correct_letter="B",
    n_options=4,
    question_chars=30,
    question_words=6,
    is_fewshot_example=False,
    scraped_at=datetime.now(UTC),
)


def make_run_id(model_key: str, variant_id: str, reasoning_mode: str) -> str:
    """Identifiant lisible et triable d'un run."""
    slug = re.sub(r"[^a-z0-9.-]+", "-", model_key.split("/")[-1].lower()).strip("-")
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return f"{slug}__{variant_id}__r{reasoning_mode}__{stamp}"


def find_resumable_run(
    paths: DataPaths,
    *,
    model_key: str,
    variant_id: str,
    reasoning_mode: str,
    sample_spec: str,
) -> str | None:
    """Cherche un run inacheve de meme configuration, a reprendre plutot qu'a recommencer.

    Un run de plusieurs heures peut etre interrompu (manque de memoire, veille, `Ctrl+C`).
    Relancer la meme commande doit alors continuer le travail entame, pas en creer un double.
    """
    candidates: list[tuple[datetime, str]] = []
    for manifest_path in paths.llm_responses_dir.glob("*.manifest.json"):
        try:
            manifest = load_manifest(manifest_path)
        except (OSError, ValueError):
            continue
        if manifest.status == "complete":
            continue
        if (
            manifest.model_key == model_key
            and manifest.prompt_variant == variant_id
            and manifest.reasoning_mode == reasoning_mode
            and manifest.sample_spec == sample_spec
            and paths.run_jsonl(manifest.run_id).exists()
        ):
            candidates.append((manifest.started_at, manifest.run_id))
    if not candidates:
        return None
    return max(candidates)[1]


def _done_question_ids(path: Any) -> set[str]:
    """Identifiants deja traites, lus dans le JSONL d'un run interrompu."""
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("error") is None and record.get("question_id"):
                done.add(str(record["question_id"]))
    return done


def run_benchmark(
    *,
    settings: Settings,
    paths: DataPaths,
    variant_id: str,
    model_key: str,
    reasoning_mode: ReasoningMode = "off",
    limit: int | None = None,
    sample: str | None = None,
    resume: str | None = None,
    max_tokens: int | None = None,
    console: Console | None = None,
    auto_grade: bool = True,
) -> RunManifest:
    """Execute un run complet et retourne son manifeste."""
    console = console or Console()
    paths.ensure_dirs()
    variant = PROMPT_VARIANTS[variant_id]

    all_questions = load_questions(paths.questions_parquet)
    questions, sample_spec = select_questions(
        all_questions, limit=limit, sample=sample, seed=settings.sample_seed
    )
    examples = {qtype: fewshot_examples(all_questions, qtype) for qtype in ("multiple", "boolean")}
    if variant.use_fewshot and not all(examples.values()):
        raise RuntimeError(
            "Aucun exemple few-shot disponible : relancer `trivia clean` pour les selectionner."
        )

    if resume is None:
        resume = find_resumable_run(
            paths,
            model_key=model_key,
            variant_id=variant_id,
            reasoning_mode=reasoning_mode,
            sample_spec=sample_spec,
        )
        if resume:
            logger.info("Run inacheve detecte, reprise de {}", resume)

    run_id = resume or make_run_id(model_key, variant_id, reasoning_mode)
    jsonl_path = paths.run_jsonl(run_id)
    manifest_path = paths.run_manifest(run_id)
    done = _done_question_ids(jsonl_path) if resume else set()
    if resume and not manifest_path.exists():
        raise FileNotFoundError(f"Aucun manifeste pour le run {run_id}")

    timeout = (
        settings.lmstudio_timeout_reasoning if reasoning_mode == "on" else settings.lmstudio_timeout
    )
    client = LMStudioClient(settings.lmstudio_base_url, timeout=timeout)

    with client:
        info = client.get_model(model_key)
        if info is None or not info.loaded:
            raise RuntimeError(
                f"Le modele {model_key} n'est pas charge dans LM Studio. "
                f"Lancer : lms load {model_key} --context-length 4096 --parallel 1 -y"
            )
        if info.parallel and info.parallel != 1:
            logger.warning(
                "Le modele est charge avec parallel={} : les latences peuvent etre biaisees "
                "par le traitement par lots. Recharger avec --parallel 1.",
                info.parallel,
            )

        generation_params: dict[str, object] = {
            "temperature": 0,
            "top_k": 1,
            "top_p": 1.0,
            "min_p": 0.0,
            "repeat_penalty": 1.0,
            "max_tokens": max_tokens or variant.max_tokens,
            "reasoning": reasoning_mode,
        }

        if resume:
            manifest = load_manifest(manifest_path)
            manifest.status = "running"
        else:
            manifest = build_manifest(
                run_id=run_id,
                variant=variant,
                model_key=model_key,
                reasoning_mode=reasoning_mode,
                model_info=info,
                generation_params=generation_params,
                dataset_path=paths.questions_parquet,
                sample_spec=sample_spec,
                sample_question_ids=(
                    [q.question_id for q in questions] if sample_spec != "all" else None
                ),
                n_questions_planned=len(questions),
            )
        save_manifest(manifest, manifest_path)

        console.print(
            f"[bold]{variant.label}[/bold] · modele [cyan]{model_key}[/cyan] · "
            f"raisonnement [cyan]{reasoning_mode}[/cyan] · "
            f"{len(questions) - len(done)} question(s) a traiter · run [dim]{run_id}[/dim]"
        )

        # Appel de chauffe : le premier appel apres chargement paie la mise en cache du prompt
        # systeme et l'allocation memoire ; il est exclu des mesures.
        warmup_request, _ = render_request(
            variant,
            WARMUP_QUESTION,
            model_key=model_key,
            reasoning_mode=reasoning_mode,
            fewshot=examples["multiple"],
            max_tokens=max_tokens,
        )
        warmup = client.complete(warmup_request)
        manifest.warmup_time_s = warmup.response_time

        # Format servi et contexte reellement applique : LM Studio peut ajuster la longueur
        # demandee, et le format decide du moteur d'inference. Les deux conditionnent la
        # comparabilite entre modeles, ils sont donc releves sur l'instance elle-meme.
        loaded = client.loaded_runtime()
        if loaded:
            manifest.model_format = loaded.get("compatibility_type")
            manifest.model_quant = loaded.get("quantization") or manifest.model_quant
            manifest.context_length = loaded.get("loaded_context_length") or manifest.context_length
        logger.info(
            "Appel de chauffe : {:.2f} s · format {} · contexte {} · moteur {}",
            warmup.response_time,
            manifest.model_format or "?",
            manifest.context_length or "?",
            manifest.runtime_engine or "?",
        )

        n_errors = 0
        n_done = len(done)
        started = datetime.now(UTC)

        with (
            jsonl_path.open("a", encoding="utf-8") as handle,
            Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TextColumn("{task.fields[status]}"),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress,
        ):
            task = progress.add_task(
                variant.id, total=len(questions), completed=len(done), status=""
            )
            for order, question in enumerate(questions):
                if question.question_id in done:
                    continue

                request, prompt_sha = render_request(
                    variant,
                    question,
                    model_key=model_key,
                    reasoning_mode=reasoning_mode,
                    fewshot=examples[question.type],
                    max_tokens=max_tokens,
                )
                response = client.complete(request)
                if response.error:
                    n_errors += 1

                handle.write(
                    json.dumps(
                        {
                            "run_id": run_id,
                            "run_order": order,
                            "question_id": question.question_id,
                            "prompt_variant": variant.id,
                            "prompt_version": manifest.prompt_version,
                            "prompt_sha256": prompt_sha,
                            "transport": request.transport,
                            "reasoning_mode": reasoning_mode,
                            "max_tokens": request.max_tokens,
                            "content": response.content,
                            "reasoning": response.reasoning,
                            "prompt_tokens": response.prompt_tokens,
                            "completion_tokens": response.completion_tokens,
                            "reasoning_tokens": response.reasoning_tokens,
                            "tokens_per_second": response.tokens_per_second,
                            "ttft_s": response.ttft_s,
                            "finish_reason": response.finish_reason,
                            "response_time": response.response_time,
                            "attempt": response.attempt,
                            "error": response.error,
                            "called_at": datetime.now(UTC).isoformat(),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                handle.flush()

                n_done += 1
                progress.update(
                    task,
                    completed=n_done,
                    status=f"{response.response_time:.2f}s · {n_errors} erreur(s)",
                )

        # L'instance a-t-elle change en cours de route ?
        final_info = client.get_model(model_key)
        if final_info is not None:
            manifest.context_length_end = final_info.context_length
            manifest.parallel_end = final_info.parallel
            manifest.instance_identifier_end = final_info.instance_identifier
            manifest.config_changed = (
                final_info.context_length != manifest.context_length
                or final_info.parallel != manifest.parallel
                or final_info.instance_identifier != manifest.instance_identifier
            )
            if manifest.config_changed:
                logger.warning(
                    "La configuration de l'instance a change pendant le run : "
                    "contexte {} -> {}, parallel {} -> {}, instance {} -> {}. "
                    "Les reponses restent valides, mais les latences sont a interpreter "
                    "avec prudence.",
                    manifest.context_length,
                    final_info.context_length,
                    manifest.parallel,
                    final_info.parallel,
                    manifest.instance_identifier,
                    final_info.instance_identifier,
                )

        manifest.n_questions_done = n_done
        manifest.n_errors = n_errors
        manifest.finished_at = datetime.now(UTC)
        manifest.status = "complete" if n_done >= len(questions) else "partial"
        save_manifest(manifest, manifest_path)

    elapsed = (manifest.finished_at - started).total_seconds() if manifest.finished_at else 0.0
    console.print(
        f"[green]Run termine[/green] · {n_done} reponses · {n_errors} erreur(s) · "
        f"{elapsed / 60:.1f} min"
    )

    if auto_grade:
        grade_runs(settings=settings, paths=paths, run_id=run_id, console=console)

    return manifest
