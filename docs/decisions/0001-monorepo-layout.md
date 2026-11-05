# 0001: Monorepo with three apps and a contract package

Status: proposed (pending review)

## Context
Three workloads with different runtime profiles: batch data processing, request serving, browser UI. Single developer for now, so one repo keeps things simple.

## Decision
One repository. `apps/pipeline`, `apps/api`, `apps/web` as independent units. `packages/api-contract` holds the OpenAPI spec as the api-to-web contract. The processed data format is the only pipeline-to-api coupling.

## Alternatives considered
- **Pipeline inside the API app:** simpler at first, but ties heavy batch work to the serving process and blocks independent scaling.
- **Separate repos:** cleaner isolation, but costly overhead for one developer and harder to change the contract atomically.

## Consequences
Cross-app changes land in one commit. Boundaries rely on the rules in `STRUCTURE.md`, not on repo walls, so they need discipline (and later, CI checks).
