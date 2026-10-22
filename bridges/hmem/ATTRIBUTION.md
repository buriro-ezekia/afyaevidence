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
