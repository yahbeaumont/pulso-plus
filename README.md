# Pulso+

Source code of Pulso+, a clinical decision support application for hypertension in Brazilian primary care. A clinician fills a structured form, an LLM agent reasons over it with six deterministic tools, and the result arrives as a suggestion to be reviewed, never as a prescription.

The engineering account of the product, with the decisions, the safety design and the evaluation, is in [case-study](case-study/README.md).

**Português:** [README.pt-BR.md](README.pt-BR.md)

## Scope

This repository is published for reading, study and review. Pulso+ is a demonstration, not a medical device: it has no regulatory clearance, it was not validated against real patient records, and the public deployment mode authenticates no institutional identity. It must not receive real patient data.

The snapshot is the application as it was developed and validated, including the operating prompt and the test suite. It is not a packaged release: it expects the environment it was built for, described below, and the session authentication layer is specific to each deployment, so you provide your own.

## How it works

`app.py` renders one page in three columns and owns the session. The domain lives in `src/has_cdss/`, with no Streamlit import inside it. The agent loop calls an OpenAI-compatible chat endpoint with tool definitions, executes the tools locally, and stops on a final message, on six turns or on sixteen tool calls. Before any network call, a preflight gate inspects the laboratory values: a raised troponin or CK-MB ends the pass with an emergency statement and a flag for human review.

The six tools are `verificar_red_flags_infarto`, `classificar_pa`, `verificar_confirmacao_pa`, `estratificar_risco_cardio`, `verificar_medicamento_sus` and `checar_contraindicacao`. Each one takes a Pydantic model and returns one, so the reasoning trail can be rendered as data and the guardrails can compare the model's text against what the tools actually produced.

Cardiovascular risk is a deterministic port of the ten-year PREVENT-CVD base model, with the coefficients of the public PyPREVENT implementation. The output declares the model's provenance and the fact that it is not calibrated for the Brazilian population.

The acceptance button only becomes available when the output is eligible and the trail is complete, and acceptance is recorded in session state. There is no database, no export to a record system and no persistence beyond the session.

## Layout

| Path | Content |
| --- | --- |
| `app.py` | Page, form, three columns, session state, acceptance flow |
| `src/has_cdss/agent.py` | Agent loop, tool dispatch, budget, prompt resolution, output parsing |
| `src/has_cdss/tools.py` | The six clinical tools |
| `src/has_cdss/prevent.py` | Ten-year PREVENT-CVD base model |
| `src/has_cdss/schemas.py` | Pydantic models for the case, tool results and final output |
| `src/has_cdss/clinical_parser.py` | Conservative extraction from text and OCR output |
| `src/has_cdss/public_network.py` | Egress guard: HTTPS, port 443, public address, pinned IP, no ambient proxy |
| `src/has_cdss/ui_review.py` | Review state and acceptance eligibility |
| `src/has_cdss/config.py` | Settings resolution and the public deployment flag |
| `prompts/system_prompt.md` | Operating instruction of the agent |
| `tests/` | Unit and regression tests, plus the synthetic fixture |
| `deploy/` | Container entrypoint, reverse proxy template, artifact verification |
| `docs/` | Validation report of the synthetic case, with screenshots |

## Requirements

Python 3.12. Tesseract with Portuguese data and Poppler for local extraction of PDFs and images. Nginx for the deployment entrypoint in `deploy/`, or any reverse proxy in front of Streamlit. An OpenAI-compatible chat endpoint that supports tool calling.

```
pip install -r requirements.txt
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `LLM_API_KEY` | Credential for the chat endpoint |
| `LLM_BASE_URL` | Base URL of the OpenAI-compatible endpoint |
| `LLM_MODEL_NAME` | Model name, which must support tool calling |
| `PULSO_PUBLIC_DEPLOY` | `1` disables `.env` loading and the fallback key, so the session must supply its own configuration |
| `PORT` | Public port used by the reverse proxy, 3000 by default |
| `PULSO_INTERNAL_PORT` | Internal Streamlit port, 8502 by default |

Secrets belong in the session or in the environment of the deployment. Nothing is read from a file that is versioned here.

## Running

```
python -m streamlit run app.py
```

For the containerised entrypoint, `deploy/start.sh` verifies the artifact, renders the proxy configuration, starts Streamlit on the internal port and puts nginx in front of it.

## Tests

```
python -m unittest discover -s tests
```

The suite covers the pressure stages at their boundaries, the confirmation rule, the risk model against reference values, the contraindication matrix, the red-flag gate, the schemas, the egress guard and the acceptance rules. It runs offline, with the endpoint mocked.

## Safety design

The red-flag gate runs before the model, so a cardiac case cannot be answered as a hypertension case. Thresholds, risk arithmetic and contraindications are code, not prompt text. Invariants applied to the model's output remove any drug name or dose that a tool did not return. The acceptance requires an eligible output, a complete trail and an explicit human confirmation.

The synthetic validation case, with the values, the trail and the screenshots, is in [docs/validacao_cenario_a_sintetico.md](docs/validacao_cenario_a_sintetico.md). The benchmark of fifty synthetic cases and the evaluation limits are described in the case study repository.

## License

MIT. See [LICENSE](LICENSE).

---

Hay Beaumont, Software Architect and Engineer. [github.com/yahbeaumont](https://github.com/yahbeaumont)
