# 0009: Map renderer and frontend libraries

Status: accepted (2026-11-06), with a Phase 4 spike on the globe

## Context
The UI needs a base map and camera, a custom GPU-rendered precipitation layer (ADR 0008), smooth zoom, and ideally a globe view for a distinctive look. The frontend is Angular (ADR 0004).

## Decision
- **MapLibre GL JS** (current npm release 6.16.0) for the base map and camera.
- The precipitation layer is a **custom WebGL layer** written by us, reading value-encoded tiles and applying a colour ramp and time interpolation in a shader.
- Wrapped in a standalone Angular component. Angular 22 (npm 22.2.4) with zoneless change detection (the default since v21), signals for state. The render loop does not depend on change detection.
- **Basemap (Proposed, decided in Phase 4 design):** a minimal, art-directed vector basemap from open data (for example Natural Earth, which is public domain), self-hosted as static files behind the CDN. Street-level detail is pointless at 0.1° data resolution.

## Evidence
- MapLibre's own docs list examples for a simple custom layer on a globe and a custom layer with tiles on a globe, so globe plus custom shader tile layers is a supported pattern (examples confirmed to exist; implementation not yet tried).
- deck.gl 9.4.1 works with MapLibre (overlaid, or interleaved in the same WebGL2 context), but its docs say globe support is only through an experimental `GlobeView` and Mercator is the fully supported projection.

## Alternatives considered
- **deck.gl:** excellent data layers, but experimental globe support and extra bundle weight.
- **OpenLayers (10.11.0):** strong WebGL data-tile support, but 2D only.
- **Leaflet (1.9.4):** no WebGL by default, so animation and shaders mean plugins.
- **CesiumJS:** full 3D globe, but heavy for our bundle target (NFR2) and more than we need.

## Risks and fallback
Custom layers on the globe need a spike. If it proves hard, ship Mercator first and add the globe as an enhancement.

## Consequences
We own the shader, which is where the distinctive visual identity lives. The renderer is isolated behind one component, so it can be swapped.
