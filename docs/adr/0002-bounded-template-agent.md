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

## Per-turn action contracts (investigator-3)

A prompt-only instruction to avoid repeated calls did not prevent an installed
small model from requesting the mandatory canonical comparison again, even after
one correction. The provider was still advertising the global action schema.

The loop now sends a finite schema generated from completed host actions and
scoped evidence. Exact follow-up choices disappear after execution; quality,
canonical comparison and memory recall remain host baselines. One matched
variant completes that analysis. Stable evidence batches are grouped by table
and reporting month and never contain records outside the frozen cutoff.
Raw comparison is a prerequisite for a brief, and the final call is reserved for
brief generation once prerequisites are met. References are constrained to shown
aliases, then checked by the existing independent brief validator. These changes
restrict scheduling and arguments; they do not select an explanation for the model.

The host checks exact menu membership and duplicates before dependency execution,
even when a provider ignores its schema. Hard call/deadline/repair limits remain
unchanged. There is no automatic scripted fallback. Fake-HTTP integration can
prove correct state transitions and formatting, but actual model acceptance must
be reported separately from those tests.
