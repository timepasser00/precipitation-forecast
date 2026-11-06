# 0004: Frontend in Angular

Status: decided by owner (2026-11-06)

## Context
The UI is map-heavy and animated, with a performance target of a useful map in under 3 s on a mid-range phone over 4G (NFR2). The owner wants Angular.

## Decision
Build `apps/web` with Angular. The map renderer is chosen in Phase 2 and wrapped as an Angular component.

## Consequences (Proposed practices, confirmed in Phase 2)
- Angular's baseline bundle is larger than minimal frameworks. Manage it with lazy-loaded routes and deferred views for the map, and enforce bundle-size budgets in the build config.
- Keep per-frame rendering and animation outside Angular change detection (outside the zone, or zoneless) so the UI stays smooth.
- The app is static output served from Cloudflare. Per Cloudflare's docs, requests to static assets are free and unlimited.
- Server-side rendering is not needed for a map app. A prerendered landing page is optional.
- Use the latest stable Angular version at the start of Phase 4 (**Verify** at that time).

## Alternatives
Not evaluated: the choice is the owner's. The main trade-off to manage is the bundle size noted above.
