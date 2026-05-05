# D-4 — Mid-stream provider/dim switch rejection

**Verdict: ✅ PASS**

## Test

Attempt to mutate `embedding_provider` + `embedding_dims` on an instance that already has indexed `case_memory` rows. The backend must refuse and surface a clear, actionable error.

## Request

```http
PUT /api/vector-stores/19
Content-Type: application/json

{
  "extra_config": {
    "embedding_dims": 384,
    "embedding_provider": "local"
  }
}
```

## Response

- **HTTP status**: `400`
- **Response body**:

```json
{
  "detail": "Refusing to mutate VectorStoreInstance embedding contract for tenant=tenant_20260406004333855618_c58c99 instance=19 — existing cases prevent: embedding_provider 'gemini' → 'local'; embedding_dims 1536 → 384. Create a new instance and reindex instead."
}
```

## Acceptance

- ✅ HTTP 4xx returned (400, as expected)
- ✅ Error body contains the substring `existing cases` — the canonical guard signal
- ✅ Error names every offending field with `before → after` deltas (`embedding_provider 'gemini' → 'local'`; `embedding_dims 1536 → 384`)
- ✅ Error tells the operator the right remediation (`Create a new instance and reindex instead`)

## Why this matters

If we silently allowed the dim swap, every subsequent search against this Qdrant collection would compute distances between a 384-d query vector and the 1536-d indexed vectors → dimensionality mismatch → cosine collapses to noise → no recall.

The guard at `services/case_embedding_resolver.reject_post_data_contract_mutation` runs **before persisting any extra_config change** in `services/vector_store_instance_service.update_instance`, comparing the proposed new shape against the actual existing `case_memory` rows that point at the instance.

## Code path

- `case_embedding_resolver.reject_post_data_contract_mutation(db, *, tenant_id, instance_id, new_extra_config)` — counts case rows for `(tenant_id, vector_store_instance_id)`; if any exist and any of `embedding_provider | embedding_model | embedding_dims` differs, raises `ValueError(...)` with the human-readable detail above.
- `services/vector_store_instance_service.update_instance` — calls the validator before writing.
- The route handler (`routes_vector_stores.update_instance`) catches `ValueError` and returns HTTP 400 with the message as `detail`.
