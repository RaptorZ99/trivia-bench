"""Lecture du moteur d'inference dans la sortie de `lms runtime ls`."""

from __future__ import annotations

from pathlib import Path

import pytest

from trivia_bench.bench import manifest

# Sortie reelle de `lms runtime ls` (LM Studio 0.4.24). Deux moteurs y sont coches en meme
# temps : LM Studio en selectionne un par format de modele.
LMS_OUTPUT = """LLM ENGINE                                        SELECTED    MODEL FORMAT
llama.cpp-mac-arm64-apple-metal-advsimd@2.34.0       ✓            GGUF
llama.cpp-mac-arm64-apple-metal-advsimd@2.33.0                    GGUF
mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0         ✓            MLX
"""

# Meme contenu, moteur MLX liste en premier : l'ordre des lignes ne doit rien changer.
LMS_OUTPUT_MLX_FIRST = """LLM ENGINE                                        SELECTED    MODEL FORMAT
mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0         ✓            MLX
llama.cpp-mac-arm64-apple-metal-advsimd@2.34.0       ✓            GGUF
"""

GGUF_ENGINE = "llama.cpp-mac-arm64-apple-metal-advsimd@2.34.0"
MLX_ENGINE = "mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0"


@pytest.fixture
def lms(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Simule un binaire `lms` present, qui renvoie la sortie de reference."""
    binary = tmp_path / "lms"
    binary.touch()
    monkeypatch.setattr(manifest, "LMS_BINARY", binary)
    monkeypatch.setattr(manifest, "_run", lambda *_, **__: LMS_OUTPUT)


@pytest.fixture
def lms_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Simule un poste sans CLI `lms` installee."""
    monkeypatch.setattr(manifest, "LMS_BINARY", tmp_path / "absent")


def test_selectionne_le_moteur_du_format_servi(lms: None) -> None:
    assert manifest.runtime_engine("gguf") == GGUF_ENGINE
    assert manifest.runtime_engine("MLX") == MLX_ENGINE


def test_l_ordre_des_lignes_est_sans_effet(lms: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manifest, "_run", lambda *_, **__: LMS_OUTPUT_MLX_FIRST)
    assert manifest.runtime_engine("gguf") == GGUF_ENGINE


def test_le_moteur_porte_sa_version(lms: None) -> None:
    engine = manifest.runtime_engine("gguf")
    assert engine is not None
    assert engine.endswith("@2.34.0")


def test_sans_format_la_premiere_ligne_cochee_sert_de_repli(lms: None) -> None:
    assert manifest.runtime_engine() == GGUF_ENGINE


def test_format_inconnu_retombe_sur_la_premiere_ligne_cochee(lms: None) -> None:
    assert manifest.runtime_engine("onnx") == GGUF_ENGINE


def test_l_en_tete_n_est_jamais_retenue(lms: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        manifest, "_run", lambda *_, **__: "LLM ENGINE     SELECTED    MODEL FORMAT\n"
    )
    assert manifest.runtime_engine("gguf") is None


def test_binaire_absent(lms_absent: None) -> None:
    assert manifest.runtime_engine("gguf") is None


def test_sortie_vide(lms: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manifest, "_run", lambda *_, **__: None)
    assert manifest.runtime_engine("gguf") is None
