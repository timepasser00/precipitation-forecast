# apps/pipeline

Fetches IFS and AIFS precipitation data from ECMWF Open Data, decodes GRIB2, derives UI-ready fields, writes to the processed store with a manifest.

Owns: scheduling, download, decoding, derivation, retention/history.
Does not own: serving data over HTTP.

Stack: decided in Phase 2.
