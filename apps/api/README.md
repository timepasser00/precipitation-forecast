# apps/api

FastAPI service. Read-only. Point forecasts on top of what the pipeline
published; tiles go straight from the CDN to the browser.

```
make synth && make api      # http://localhost:8000/docs
```

Endpoints, errors, caching and configuration: [`docs/api.md`](../../docs/api.md).
The contract is [`packages/api-contract/openapi.json`](../../packages/api-contract/openapi.json);
after changing any route or model run `make openapi` (CI fails on drift).

Layout: `app.py` routes, `models.py` response models, `state.py` manifest cache + cube LRU,
`sampling.py` bilinear point sampling, `settings.py` environment config.

The API never imports pipeline code. It shares only `packages/precip-core` (codec, manifest,
storage, registry).
