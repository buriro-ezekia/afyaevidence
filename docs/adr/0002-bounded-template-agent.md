# ADR 0002: strict actions and server-rendered candidate briefs

Status: implemented for the operator agent loop, 22 October 2026.

The existing calculation slice has no third-party runtime Python dependencies.
For this bounded CLI, use an explicit standard-library action validator and a
matching exported JSON Schema. Reject extra keys/types, duplicate keys and invalid
references. Keep the proposed future HTTP Pydantic request schemas separate; no
HTTP service is claimed by this slice. Schema-export consistency and adversarial
validation tests are required when actions change.

The model selects follow-up tools and proposes a reviewed explanation code with
host references. It cannot supply trusted arithmetic, source scopes or approval.
The host verifies category prerequisites and renders all numeric statements and
qualitative templates. This trades unrestricted prose for inspectable, bounded
behaviour on synthetic reporting scenarios. It remains a model-driven action loop
when an actual provider is used; scripted policy is explicitly labelled and cannot
satisfy actual-model acceptance. No expected scenario key is in model context.

Reference/schema checks alone cannot establish free-text causal truth. Accordingly,
this increment does not accept free-form clinical explanations. All candidates
remain awaiting human review. Broader reasoning and prose may be added only with
separate semantic evaluation and review controls; they are not implied by this
implementation. Optional Meterless Runtime inference remains separate from actual
H-MEM reference use and the implemented Ollama provider.
