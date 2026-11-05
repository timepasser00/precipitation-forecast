# apps/api

Serves processed forecast data over HTTP. Documented via the OpenAPI spec in `packages/api-contract`.

Owns: endpoints, validation, caching, auth/rate-limiting if needed.
Does not own: downloading or decoding GRIB files. Reads the processed store only.

Stack: decided in Phase 2.
