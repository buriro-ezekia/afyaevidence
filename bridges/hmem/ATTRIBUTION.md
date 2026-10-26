# Meterless H-MEM attribution

The `upstream/src` files, `upstream/package.json`, `upstream/README.md` and `upstream/LICENSE` are copied
unchanged from Meterless/Meterless commit
`1742dec56a66e58eef9dda2d2b865823758ca8cd` (Apache-2.0). Their original location is
`engines/hmem/reference/`, except the licence, which comes from the repository root.
The adapter `helper.mjs` is new AfyaEvidence integration code.

The source is a reference prototype with deterministic mock hash embeddings and
JSON-file persistence. It is not a production memory library, vector database,
medical knowledge source or tamper-proof audit ledger. Dreaming, consolidation,
mining, automatic approval and conflict auto-resolution are not exposed by this
bridge. Source SHA-256 hashes are pinned in `upstream.lock.json` and verified before
launch. Upstream's optional development/test dependencies are not used or copied.
Node 24's experimental TypeScript transform executes the original TypeScript
without transpiling or rewriting upstream files. No npm runtime package is needed.

## Bundled reference documentation

The upstream `README.md` is preserved verbatim for provenance. Its links to `../AGENTS.md` and `../examples/`, and its example execution command, refer to the layout of the original Meterless source repository. Those parent-level specification and example files are not part of this pinned AfyaEvidence integration subset; the relative links therefore do not resolve here. This does not affect the pinned reference code or the verified Node 24 bridge. For AfyaEvidence setup and verification, use [the H-MEM bridge guide](../../docs/HMEM_BRIDGE.md) and the root project README instead of the upstream example commands.
