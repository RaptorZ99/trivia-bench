"""Invocation de dbt pour construire la couche gold.

DuckDB n'autorise qu'un seul ecrivain, ou plusieurs lecteurs, mais jamais les deux : un
dashboard qui garderait une connexion ouverte bloquerait la construction. On construit donc
dans un fichier temporaire, puis on le met en place par un remplacement atomique, ce qui laisse
les lecteurs en cours terminer sur l'ancienne version.

Les chemins relatifs de dbt-duckdb sont resolus depuis le repertoire courant : les commandes
sont donc toujours lancees depuis la racine du depot.
"""

from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console

from trivia_bench.config import Settings
from trivia_bench.logging import logger

DBT_DIR = "dbt"


def run_dbt_build(
    settings: Settings,
    *,
    full_refresh: bool = False,
    select: str | None = None,
    console: Console | None = None,
    project_dir: str = DBT_DIR,
) -> bool:
    """Lance `dbt build` vers un fichier temporaire, puis publie le resultat."""
    from dbt.cli.main import dbtRunner

    console = console or Console()
    final_path = Path(settings.duckdb_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)

    # La construction se fait dans un sous-dossier temporaire, sous le meme nom de fichier :
    # dbt-duckdb derive le nom du catalogue du nom de fichier, donc changer ce dernier
    # invaliderait les references qualifiees stockees dans les vues.
    build_dir = final_path.parent / ".build"
    build_dir.mkdir(parents=True, exist_ok=True)
    build_path = build_dir / final_path.name

    for stale in (build_path, build_path.with_name(build_path.name + ".wal")):
        if stale.exists():
            stale.unlink()

    env_backup = {key: os.environ.get(key) for key in ("TRIVIA_DUCKDB_PATH", "TRIVIA_SILVER_DIR")}
    os.environ["TRIVIA_DUCKDB_PATH"] = str(build_path)
    os.environ["TRIVIA_SILVER_DIR"] = str(settings.silver_dir)

    args = [
        "build",
        "--project-dir",
        project_dir,
        "--profiles-dir",
        project_dir,
        "--target",
        "prod",
    ]
    if full_refresh:
        args.append("--full-refresh")
    if select:
        args += ["--select", select]

    console.print(f"[dim]dbt {' '.join(args)}[/dim]")
    try:
        result = dbtRunner().invoke(args)
    finally:
        for key, value in env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    if not result.success:
        logger.error("dbt build a echoue : {}", result.exception or "voir la sortie ci-dessus")
        _discard(build_path)
        return False

    # dbt garde sa connexion ouverte apres l'invocation : tant qu'elle n'est pas fermee et
    # que DuckDB n'a pas ecrit son point de controle, le fichier ne contient pas encore les
    # tables. Il faut donc fermer avant de le publier, sinon on deplace un fichier vide.
    _close_adapters()
    n_objects = _checkpoint(build_path)
    if n_objects == 0:
        logger.error("La base construite est vide : publication annulee.")
        _discard(build_path)
        return False

    # Remplacement atomique : un dashboard qui lit encore l'ancien fichier n'est pas interrompu.
    build_path.replace(final_path)
    logger.info("Couche gold publiee dans {} ({} objets)", final_path, n_objects)
    console.print(f"[green]Couche gold construite[/green] · {final_path} · {n_objects} objets")
    return True


def _close_adapters() -> None:
    """Ferme les connexions ouvertes par dbt pour que DuckDB ecrive son point de controle."""
    try:
        from dbt.adapters.factory import reset_adapters
    except ImportError:  # pragma: no cover - depend de la version de dbt
        logger.warning("Impossible de fermer les connexions dbt : API introuvable.")
        return
    reset_adapters()  # type: ignore[no-untyped-call]


def _checkpoint(path: Path) -> int:
    """Force l'ecriture du point de controle et retourne le nombre d'objets crees."""
    import duckdb

    if not path.exists():
        return 0
    with duckdb.connect(str(path)) as connection:
        connection.execute("CHECKPOINT")
        count = connection.execute("select count(*) from information_schema.tables").fetchone()
    return int(count[0]) if count else 0


def _discard(build_path: Path) -> None:
    """Supprime le fichier de construction et son journal."""
    for path in (build_path, build_path.with_name(build_path.name + ".wal")):
        if path.exists():
            path.unlink()
