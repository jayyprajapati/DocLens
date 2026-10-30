# Quality gates for DocLens. `make check` before every commit that touches prompts, retrieval,
# guardrails or Brain; `make eval` (needs Brain + Mongo + a BYOK key, costs API calls) before merging.
PY ?= .venv/bin/python
MODEL ?= gpt-oss:20b
PROVIDER ?= ollama_cloud
BASELINE ?= baseline-201
LABEL ?= candidate

.PHONY: test check eval compare retrieval-eval

test check:            ## offline guardrail / grounding / pipeline tests (~0.2 s)
	$(PY) -m pytest tests -q

eval:                  ## end-to-end accuracy eval; needs BRAIN_API_KEY and EVAL_API_KEY in the env
	$(PY) evals/run_eval.py --label $(LABEL) --provider $(PROVIDER) --model $(MODEL) --concurrency 4

compare:               ## regression gate vs the stored baseline (exit 1 if overall drops > 1 pt)
	$(PY) evals/compare.py $(BASELINE) $(LABEL) --max-drop 1.0

retrieval-eval:        ## retrieval-only recall (free, no LLM)
	$(PY) evals/retrieval_eval.py --split dev
