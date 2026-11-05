# Data sources: ECMWF Open Data

Facts below come from ECMWF's own pages (checked 2026-11-06). Re-verify before relying on them, as ECMWF changes this service.

| Item | Detail |
|---|---|
| Models | IFS (HRES control + 50-member ENS), AIFS Single, AIFS ENS |
| Run times | 00, 06, 12, 18 UTC |
| Resolution | IFS: 0.25° and, since 20 Oct 2026, 0.1°. AIFS: 0.25° only |
| IFS 0.1° | Published about 2 h after 0.25°. Split into surface (`-sfc`) and pressure-level (`-pl`) files. 0.25° stays combined |
| Steps | IFS 00/12z: 0-144 h every 3 h, then 6-hourly to 360 h. IFS 06/18z: shorter (HRES to 90 h). AIFS: 6-hourly to 360 h |
| Format | GRIB edition 2 (BUFR 4 for cyclone tracks) |
| Retention | Last 12 runs only |
| Access | data.ecmwf.int, plus AWS, Azure, Google Cloud mirrors. Python client `ecmwf-opendata` can pick the source |
| Portal limits | 500-2000 simultaneous connections, varies |
| Licence | CC-BY-4.0 plus ECMWF Terms of Use. Redistribution and commercial use allowed with attribution |
| Extra products | Post-processed ensemble stats and daily-precipitation probabilities exist |

## Open items to confirm in Phase 3

- Exact `tp` (total precipitation) definition, units and accumulation convention for IFS vs AIFS. Not covered in the pages checked.
- Exact attribution wording required in the UI.
- Whether we need 0.1° at all, or whether 0.25° is enough for the experience.
