# 0011: Compute, hosting and scheduling

Status: accepted as baseline (2026-11-06). Provider details to re-verify at order time.

## Context
One small machine must run the pipeline and API within a $10/month target (DESIGN section 10). Users are served mostly from the CDN.

## Decision
- **One small VM at Hetzner, Germany or Finland.** Hetzner's own page (2026-11-06) lists CX23 (2 vCPU x86, 4 GB RAM, 40 GB NVMe) at €5.99/month and CAX11 (ARM) at €6.49, excluding VAT, 20 TB traffic included in the EU. Singapore is not listed for these plans. Default pick: **CX23** (x86, simplest). Python wheels exist for ARM too, so CAX11 stays an option.
- **Why EU is fine:** users hit the CDN, and API calls are cached. ECMWF is European, so fetching from an EU VM is likely the fastest path (measure in Phase 3).
- **Scheduling:** `systemd` timers run an idempotent CLI (for example `pipeline run --source ecmwf-ifs --latest`). Around each expected publication time it polls until the run is complete, then publishes. Safe to re-run.
- **API** runs on the same VM behind the Cloudflare proxy, with cache headers (ADR 0006).
- **Deployment:** containers are preferred for reproducibility and rollback (**Proposed**, finalised in Phase 3).
- **Observability:** structured logs, a health endpoint with data-freshness, an external uptime monitor on a free tier, Cloudflare analytics for hit ratio.
- **Backups:** none for data (re-derivable from ECMWF within its 12-run window). Config lives in git.

## Verify
- The Hetzner page marked all listed plans as currently unavailable, and a third-party report earlier showed €5.49 and €5.99 for CX23 and CAX11. Confirm price, stock, VAT and the IPv4 charge at order time. With those and a domain, the total may approach the $10 target.
- 4 GB RAM should be enough: one full 0.1° global float32 field is about 26 MB and fields are processed one at a time. Measure in Phase 3.

## Alternatives considered
- **Airflow, Prefect or Dagster:** too heavy for a few sources and four runs a day.
- **GitHub Actions cron:** free-ish but timing is loose and runners are ephemeral. Not a fit for a polling publisher.
- **ECMWF push notifications (WIS2):** possible later. Polling is simpler.
- **Serverless pipeline:** execution limits and cost are unclear for decode-heavy work.
- **Singapore VM:** closer to India but far costlier (CPX12 at €15.99 for 1 vCPU, 2 GB per Hetzner's Singapore page) and unnecessary behind a CDN.

## Consequences
One fixed-price machine, no autoscaling, matching the cost guardrails.
