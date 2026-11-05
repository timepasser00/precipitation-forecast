# packages/api-contract

`openapi.json` is the contract between `apps/api` and `apps/web`. It is **generated** from the
FastAPI app (`make openapi`), committed, and checked in CI so it cannot drift. The Angular client
is generated from it in Phase 4. Do not edit it by hand.
