LMS ?= $(HOME)/.lmstudio/bin/lms
MODEL ?= google/gemma-4-12b-qat
CONTEXT ?= 4096

.PHONY: help setup lint format test typecheck check scrape clean-data load-model unload-model \
        bench bench-all grade build docs dashboard all

help:  ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup:  ## Installe l'environnement et les hooks git
	uv sync
	uv run pre-commit install

lint:  ## Lint + verification du formatage
	uv run ruff check .
	uv run ruff format --check .

format:  ## Formate le code
	uv run ruff check --fix .
	uv run ruff format .

test:  ## Lance les tests
	uv run pytest

typecheck:  ## Verifie le typage statique
	uv run mypy src

check:  ## Verifie LM Studio (Phase 0)
	uv run trivia check

scrape:  ## Telecharge les questions OpenTDB (necessite un reseau non filtre)
	uv run trivia scrape

clean-data:  ## Bronze -> silver questions.parquet
	uv run trivia clean

load-model:  ## Charge le modele dans LM Studio
	$(LMS) server start
	$(LMS) load $(MODEL) --context-length $(CONTEXT) --gpu max --parallel 1 --identifier trivia-bench -y

unload-model:  ## Decharge le modele
	$(LMS) unload --all

bench:  ## Lance une variante (make bench VARIANT=v1_letter)
	uv run trivia bench --variant $(VARIANT)

bench-all:  ## Lance les 5 variantes
	uv run trivia bench --all-variants

grade:  ## Note tous les runs (bronze -> silver answers)
	uv run trivia grade --all

build:  ## Construit la couche gold avec dbt
	uv run trivia build

docs:  ## Genere la documentation dbt statique dans docs/dbt/
	uv run dbt docs generate --project-dir dbt --profiles-dir dbt --target prod --static
	@mkdir -p docs/dbt
	@cp dbt/target/static_index.html docs/dbt/index.html
	@echo "Documentation dbt : docs/dbt/index.html"

dashboard:  ## Lance le dashboard Streamlit
	uv run streamlit run app/app.py

all: lint typecheck test  ## Lint + typage + tests
