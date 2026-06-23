DOCKER ?= $(firstword $(wildcard /usr/local/bin/docker /usr/bin/docker /bin/docker) docker)
COMPOSE = $(DOCKER) compose -f docker-compose.yml
IN_DOCKER := $(wildcard /.dockerenv)
OLLAMA_HOST ?= http://ollama:11434
OLLAMA_MODEL ?= qwen3:0.6b
SCRAPE_START ?= 01.07.2007
SCRAPE_END ?= 23.06.2026
SCRAPE_SLEEP ?= 2
SCRAPE_ARGS ?=

ifeq ($(IN_DOCKER),)
ANNOTATE_CMD = $(COMPOSE) run --rm app uv run src/annotate/run_annotate.py --use-llm
COMPARE_CMD = $(COMPOSE) run --rm app uv run src/compare_ground_truth/run_compare.py
LLM_SETUP_CMD = $(COMPOSE) --profile setup run --rm ollama-pull
else
ANNOTATE_CMD = uv run src/annotate/run_annotate.py --use-llm
COMPARE_CMD = uv run src/compare_ground_truth/run_compare.py
LLM_SETUP_CMD = curl -fsS $(OLLAMA_HOST)/api/pull -H 'Content-Type: application/json' -d '{"name":"$(OLLAMA_MODEL)","stream":false}'
endif

.PHONY: scrape extract docker-up docker-down llm-setup annotate compare-ground-truth

scrape:
	uv run src/scrape/run_scrape.py --start-date $(SCRAPE_START) --end-date $(SCRAPE_END) --sleep-seconds $(SCRAPE_SLEEP) $(SCRAPE_ARGS)

extract:
	uv run src/extract/run_extract.py

enter-docker:
	docker compose exec app bash

docker-up:
	$(COMPOSE) up -d db ollama app

docker-down:
	$(COMPOSE) down

llm-setup:
	$(LLM_SETUP_CMD)

annotate:
	$(ANNOTATE_CMD)

compare-ground-truth:
	$(COMPARE_CMD)
