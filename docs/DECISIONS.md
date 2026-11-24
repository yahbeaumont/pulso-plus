# Decisions

Eight choices shaped Pulso+. Each entry states the decision, the alternatives that were considered, and what it costs.

## 1. Streamlit instead of a split frontend

The interface is one Streamlit page, not a React application over a FastAPI service.

The alternative was the conventional split, and it would have produced a better product for a team and a worse one for this stage. The state that matters here is a single session holding a form, a trail and an output, and Streamlit gives that state for free with server-side rendering and no client build. The cost is real: layout control is coarse, the three columns are a compromise at narrow widths, and there is no client-side interactivity beyond what the widgets provide. For a clinical tool that is read, not operated, that trade was acceptable.

The decision is reversible in the direction that matters. The domain package has no Streamlit import, so a FastAPI surface over the same tools is a new adapter, not a rewrite.

## 2. A model with tools instead of a model that answers

The clinical logic lives in six functions, and the model orchestrates them. The alternative, one long prompt with the protocol embedded and a structured output schema, would have been faster to build and impossible to audit.

With tools, the trail shows which thresholds were applied and with which inputs, and a reviewer can recompute any value. The model's contribution is reduced to selection and explanation, which is the part of the work a language model actually does well: reading a messy case, noticing that a lipid panel is missing, and choosing the next check.

The cost is latency and a new failure surface. Each tool call is a round trip, and a model that calls the wrong tool in the wrong order produces a trail that looks thorough and answers a different question. The budget of six turns and sixteen calls limits the second problem without solving it.

## 3. The red-flag gate outside the model

The acute coronary check is a function that runs before the endpoint is contacted, not an instruction in the prompt.

The alternative was to tell the model, in strong terms, that chest pain with raised markers requires emergency referral. Models follow such instructions most of the time, and "most of the time" is the wrong quantity for a triage decision. Moving the check into code makes the behaviour testable, and makes the failure mode a refusal rather than a confident paragraph.

The cost is scope. A code gate covers what it enumerates, and the enumeration is short. A model with a broad instruction might catch a presentation the gate does not, which is exactly why the gate is described as narrow in the documentation rather than as a general safety layer.

## 4. PREVENT ported, not called

The ten-year risk model is implemented in Python from published coefficients, not consumed from an API.

A port is deterministic, testable and offline, and the interface can state the provenance and the calibration limit next to the number. An API would have been less code and more dependencies, and it would have made the score unavailable whenever the network was.

The cost is maintenance. A coefficient update upstream is a code change here, and there is no automatic signal that it happened. The alternative score for the Brazilian population does not exist in a form that could be ported, which is why the output carries the calibration caveat instead of a better model.

## 5. OCR local, review mandatory

Extraction runs in the process, with Tesseract and Poppler, and the result is always a proposal the clinician confirms.

The alternative was to send the document to the model and let it read. That is more capable and worse on two axes: the document leaves the application, and the extraction becomes unverifiable, because the model's reading of a lab report is a sentence rather than a field. A parser that recognizes a small set of patterns and refuses everything else is duller and auditable.

The cost is coverage. Handwriting, rotated scans and unusual layouts produce empty fields. The form makes that visible, and the clinician types the value, which is the same work as before the feature existed and never worse.

## 6. Acceptance in session state only

There is no database, no export and no integration with a record system. The accepted state lives in the session.

This was the only defensible choice for a demonstration that authenticates nobody. A tool that stores patient data without identity, retention policy or access control is a liability, and adding storage to make the demo feel complete would have been the wrong direction. The absence is documented as a limit rather than presented as a privacy feature.

The cost is that the product cannot be used in a real workflow. That is accurate: it cannot.

## 7. The public mode has no fallback key

The deployment flag disables `.env` loading and the global key, so a public instance without a session key cannot call the engine at all.

The alternative, a shared key with a rate limit, is the usual shortcut and the one that leaks first. Making the public build inert without a per-session key means the demonstration cannot become an anonymous proxy for someone else's quota.

The cost is friction: a visitor who wants to try the full flow needs a key. The screenshot walkthrough exists for that reason.

## 8. Report the disagreement rate

The benchmark result, 40 percent agreement over 50 synthetic cases, is in the README.

The alternative is to publish the parts that flatter the system: the test count, the absence of critical errors, the gate. The agreement rate is the number a clinician would ask for first, and leaving it out would make every other claim in the repository suspect.

The cost is that the project reads as less finished than it could. That is the correct impression. A decision support tool that agrees with a careful reference four times in ten is a second reader, and the repository should say so before someone discovers it in use.
