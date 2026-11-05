# apps/web

The browser UI. Consumes the API using types derived from `packages/api-contract`.

Owns: visual design, interaction, map/animation rendering.
Does not own: any data processing. If the UI needs a derived value, ask for it in the API.

Stack: decided in Phase 2.
