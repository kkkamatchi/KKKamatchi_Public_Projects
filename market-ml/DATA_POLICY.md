# Data policy

Most market data may be viewed but not redistributed, and some may not be used to train models at all. This repo therefore ships code and synthetic fixtures; users fetch data themselves under their own terms.

## Rules

1. **No data files or weights in git.** `tools/ci/check_raw_data.py` blocks data, archive and model-weight files (`.csv`, `.parquet`, `.json`, `.zip`, `.joblib`, `.safetensors` and more, in any position, so `.csv.bz2` counts), notebooks saved with outputs, and anything over 500 KB. Paths in `.raw-data-allow` are exempt; only synthetic fixtures go there. The check catches accidents, not deliberate evasion: review every diff before it goes public.
2. **Every published artifact declares its inputs.** A dataset, model weights, published metrics, or a reference table gets a `provenance.toml` beside it:

   ```toml
   artifact = "short name"
   kind = "dataset"           # dataset | weights | metrics | reference-facts
   licence = "Apache-2.0"     # the artifact's own licence
   [[inputs]]
   source = "ecb-reference-rates"   # an id from licences/sources.toml
   as_of = 2026-11-03
   ```

3. **Weights and datasets are published to Hugging Face, never committed.** The release job that uploads an artifact must run the licence gate on that artifact's `provenance.toml` first and refuse to upload if it fails (built with the first release, P2).
4. **The licence gate decides.** `tools/ci/licence_gate.py` fails when a source is unknown, denied without written permission, or still marked `verify`; when the source may not feed that kind of artifact; or when a share-alike source feeds an artifact under another licence.
5. **Indian exchange and broker data stay out.** NSE, BSE, MCX and Kite Connect data, and anything derived from them (datasets, weights, metrics), are denied unless written permission is recorded in `permission_ref`. Charge schedules cited from NSE circulars are facts and may feed `reference-facts` only.
6. **Re-read terms before each release.** Terms change. Each registry entry records when it was last `checked`.

## Adding a source

Add a `[[source]]` entry to `licences/sources.toml` with the terms URL, the licence in a few words, a `status`, the `allowed_kinds`, `checked` (the date you read the terms) and notes. Start new sources at `status = "verify"` and change the status only after reading the current terms.
