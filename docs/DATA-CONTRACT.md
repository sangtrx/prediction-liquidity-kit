# Bootstrap data-contract principles

Future typed models must preserve:

- venue/program/rule-version identity;
- effective-from/effective-to timestamps;
- source provenance and snapshot/hash;
- market/event identity;
- decimal money/rate inputs;
- observed vs estimated vs synthetic classification;
- missing/unknown state distinct from numeric zero;
- deterministic replay configuration and seed where applicable.

Exact field schemas belong to the owning implementation Issues and should not be invented prematurely.
