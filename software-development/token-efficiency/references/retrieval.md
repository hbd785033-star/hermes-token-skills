# Retrieval: Finding Evidence Without Reading Everything

Load this reference when searching code, working in a large or unfamiliar repository, or tracing symbols across files.

## Routing

```text
Known file or symbol
    ↓
Hermes targeted search/read

Semantic tools available
    ↓
Prefer Serena-style symbol retrieval

Broad unfamiliar repository
    ↓
Repomix with include/exclude filters

Do NOT:
pack an entire repo for one-function questions
```

## Targeted search first

Use the narrowest available operation, in this order:

1. exact symbol, phrase, filename, or key search;
2. search with zero or minimal context;
3. targeted file or page-section read;
4. expand around a confirmed hit;
5. full read only when structure or exact completeness requires it.

Build a cheap map before reading content:

- Codebases: top-level structure, language/framework indicators, manifests, entry points, relevant symbols or filenames, tests adjacent to the target behavior.
- Web research: candidate URLs, titles, dates, publishers, short snippets, source authority and recency.
- Datasets/APIs: schema or keys, item counts when a tool provides them, a tiny representative sample, the fields the task needs.

Prefer `search_files(target='files')`, `search_files(output_mode='files_only'|'count')`, compact browser snapshots, or DOM extraction over full-content reads.

## Symbol neighborhood

For code, a confirmed symbol is read together with its neighborhood:

- definition;
- direct callers or imports;
- configuration affecting it;
- tests proving expected behavior.

**Async / adapter / registry boundaries:** when a trace ends at a boundary, include the worker, callback, registry, or adapter that links two confirmed symbols. A narrow context that omits the decisive call edge is a wrong context, not a cheap one.

## Serena (optional acceleration backend)

Serena is an optional acceleration backend, never a hard dependency.

- Check availability first (MCP configured, tools listed). If absent, follow the same retrieval pattern with Hermes file/search tools.
- Use it for symbol-level semantic retrieval: definitions, references, symbol neighborhoods.
- Caveat: symbol retrieval can miss runtime registration, generated code, reflection, or configuration-driven behavior. Verify those paths separately.

## Repomix (broad repositories only)

Use Repomix for broad understanding of a large or remote repository when ordinary targeted search is insufficient.

- Start with `--include` and exclusions; add `--compress` only for large repositories.
- Write output outside the project unless the user requests an artifact.
- Do not pack an entire repository for a one-symbol lookup.
- Do not trust automatic secret filtering as the only security boundary. Review includes/excludes, and explicitly exclude credentials, environment files, keys, and private data before sharing packed output.

## Large repository strategy

1. Map the tree and manifests; rank likely evidence locations.
2. Search for the target symbol or term; confirm hits.
3. Read each hit plus its symbol neighborhood.
4. Only if targeted search cannot answer the question, pack a filtered subset with Repomix and search the packed output before reading it.

Context selection is budget-constrained. If a map or index says a file is irrelevant, do not read it "just in case"; record why it was excluded.
