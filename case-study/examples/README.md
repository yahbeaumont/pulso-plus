# Examples

Three small excerpts of the patterns used in Pulso+, rewritten for illustration. They are not the product source: the real implementations carry the full protocol tables, the complete coefficient set and the validation the product depends on.

| File | Pattern |
| --- | --- |
| `tool_contract.py` | A clinical tool as a typed function, so the trail is data and the thresholds are testable |
| `preflight_gate.py` | A refusal that runs before the model is called, with the test that guards it |
| `egress_guard.py` | Validating and pinning the address of a configurable endpoint before opening a connection |

Each file runs on its own with the standard library plus Pydantic for the first one.
