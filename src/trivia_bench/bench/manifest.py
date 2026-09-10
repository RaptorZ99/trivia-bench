"""Construction du manifeste d'un run : tout ce qu'il faut pour rejouer et auditer.

Un benchmark n'a de valeur que si l'on sait exactement dans quelles conditions il a tourne :
version du modele et de sa quantification, parametres de generation, version des gabarits de
prompt, empreinte du jeu de questions, versions logicielles et machine.
"""

from __future__ import annotations

import json
import platform
import plistlib
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from trivia_bench import __version__
from trivia_bench.bench.lmstudio import ModelInfo
from trivia_bench.bench.prompts import PromptVariant, prompt_version
from trivia_bench.ids import file_sha256
from trivia_bench.logging import logger
from trivia_bench.models import ReasoningMode, RunManifest

LMSTUDIO_PLIST = Path("/Applications/LM Studio.app/Contents/Info.plist")
LMS_BINARY = Path.home() / ".lmstudio" / "bin" / "lms"


def _run(args: list[str], timeout: float = 15.0) -> str | None:
    """Execute une commande courte et renvoie sa sortie, ou `None` en cas d'echec."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def lmstudio_version() -> str | None:
    """Version de l'application LM Studio installee."""
    if not LMSTUDIO_PLIST.exists():
        return None
    try:
        with LMSTUDIO_PLIST.open("rb") as handle:
            data = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return None
    version = data.get("CFBundleShortVersionString")
    return str(version) if version else None


def runtime_engine() -> str | None:
    """Moteur d'inference selectionne (`lms runtime ls`)."""
    if not LMS_BINARY.exists():
        return None
    output = _run([str(LMS_BINARY), "runtime", "ls"])
    if not output:
        return None
    for line in output.splitlines():
        if "✓" in line:
            return line.split()[0]
    return None


def git_sha() -> str | None:
    """Commit courant du depot, s'il y en a un."""
    return _run(["git", "rev-parse", "HEAD"])


def machine_info() -> dict[str, str]:
    """Description succincte de la machine."""
    info: dict[str, str] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }
    cpu = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    if cpu:
        info["cpu"] = cpu
    memory = _run(["sysctl", "-n", "hw.memsize"])
    if memory and memory.isdigit():
        info["memory_gb"] = f"{int(memory) / 1024**3:.0f}"
    macos = _run(["sw_vers", "-productVersion"])
    if macos:
        info["macos"] = macos
    return info


def build_manifest(
    *,
    run_id: str,
    variant: PromptVariant,
    model_key: str,
    reasoning_mode: ReasoningMode,
    model_info: ModelInfo | None,
    generation_params: dict[str, object],
    dataset_path: Path | None,
    sample_spec: str,
    sample_question_ids: list[str] | None,
    n_questions_planned: int,
) -> RunManifest:
    """Assemble le manifeste au demarrage d'un run."""
    return RunManifest(
        run_id=run_id,
        model_key=model_key,
        model_display_name=model_info.display_name if model_info else None,
        model_quant=model_info.quantization if model_info else None,
        model_size_bytes=model_info.size_bytes if model_info else None,
        instance_identifier=model_info.instance_identifier if model_info else None,
        context_length=model_info.context_length if model_info else None,
        parallel=model_info.parallel if model_info else None,
        prompt_variant=variant.id,
        variant_label=variant.label,
        prompt_version=prompt_version(),
        reasoning_mode=reasoning_mode,
        transport="api_v0" if variant.structured else "native",
        generation_params=dict(generation_params),
        lmstudio_version=lmstudio_version(),
        runtime_engine=runtime_engine(),
        python_version=sys.version.split()[0],
        package_version=__version__,
        git_sha=git_sha(),
        dataset_sha256=file_sha256(dataset_path)
        if dataset_path and dataset_path.exists()
        else None,
        sample_spec=sample_spec,
        sample_question_ids=sample_question_ids,
        n_questions_planned=n_questions_planned,
        machine=machine_info(),
        started_at=datetime.now(UTC),
        status="running",
    )


def save_manifest(manifest: RunManifest, path: Path) -> None:
    """Ecrit le manifeste sur disque."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.debug("Manifeste ecrit dans {}", path)


def load_manifest(path: Path) -> RunManifest:
    """Relit un manifeste existant."""
    return RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
