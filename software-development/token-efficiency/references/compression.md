# Compression: Reducing What Already Entered Context

Load this reference when reducing tool output, choosing a data representation, or considering LLMLingua/TOON.

## Order of operations

```text
first eliminate irrelevant content

then reduce representation overhead

only then consider model-based compression
```

Compression is the last step, not the first. Most savings come from not loading content at all.

## Tool-output reduction

When tool calls would return large or repetitive output, use `execute_code` to call tools programmatically and print only the reduced result. Decide by output volume and repetition, not by call count.

Keep:

- source identifiers and paths;
- matched lines or fields;
- counts needed for decisions;
- errors and uncertainty;
- enough local context to verify interpretation.

Drop:

- duplicate records;
- repeated stack frames;
- unchanged boilerplate;
- irrelevant metadata;
- generated, vendor, cache, and binary paths unless directly relevant.

For browser pages, use `browser_console` to extract structured fields from the DOM instead of repeatedly loading full page text.

**Logs:** group identical errors; keep the first and last relevant occurrence plus counts and timestamps needed for the decision.

## Representation selection

Choose the format by data shape:

| Data shape | Preferred representation |
|---|---|
| Short prose evidence | concise bullets with source pointers |
| Code relationships | symbol/path map |
| Uniform records with identical fields | compact table; TOON only when supported and beneficial |
| Deeply nested or irregular data | JSON or YAML; do not force TOON |
| Repository overview | ranked file/symbol map |
| Long logs | grouped errors + first/last relevant occurrence |
| Small human-facing results | plain text or a Markdown table |

Never convert data merely because a compact format exists. Conversion overhead and ambiguity can cost more than they save.

## TOON (optional)

Consider TOON only for **large uniform structured records**: large arrays whose objects share the same fields, when both producer and consumer understand the format.

For small data, deep nesting, or irregular structures, prefer ordinary Markdown, JSON, or YAML.

## LLMLingua (optional escalation)

LLMLingua is an optional escalation, never automatic.

- Use it only when a compatible compressor is already available or the user approves installation. Never install it silently.
- Apply it only to prose that is still oversized after manual reduction (constraint/evidence separation).
- Preserve instructions, acceptance criteria, identifiers, numbers, negations, citations, and code.
- Re-verify the compressed prompt against the original constraints before use.
- A compressor that requires expensive inference may not reduce total cost; measure end-to-end when possible.

## Provenance

Every compressed fact keeps its file path, URL, record ID, or line range. If compression causes ambiguity, discard the compressed form and reopen the relevant source section.
