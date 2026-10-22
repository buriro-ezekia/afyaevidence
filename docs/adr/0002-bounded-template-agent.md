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

## CPU scheduling (investigator-4)

The operator's four-call run spent 134.14, 138.41 and 201.18 seconds on exploration
and exhausted the 600-second deadline during its fourth request. Reserving a call
alone did not reserve inference time. The CPU profile therefore collects raw
diagnostics along with quality, canonical facts and scoped memory before dispatch,
allows one actual model-selected follow-up, then makes the second call brief-only.
The first timeout reserves `min(request_timeout, deadline / 2)` seconds for the
brief; all dispatches are bounded by remaining time. Invalid output fails within
the two-call limit, with no automatic repair or scripted replacement.

Fresh phase projections retain all canonical facts, raw positive prerequisites,
quality exclusions, scoped source indexes and historical notes. A compact menu
grounds follow-up selection in prompt text; the full schema occurs only in Ollama's
format field. The final prompt has only the brief policy, scoped facts, selected
follow-up result and reference requirements. Full records/provenance remain in the
receipt. This preserves informed model selection while reducing context. The
standard four-call/one-repair profile remains available explicitly.

An initial real CPU fixture run reached the brief in 168.58 seconds but omitted a
mandatory synthetic-data limitation. That failed receipt is retained. The phase
schema now constrains mandatory review codes in addition to the independent host
validator; the host does not fill in missing codes or approve a candidate.
