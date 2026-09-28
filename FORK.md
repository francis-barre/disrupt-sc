# Fork changes

This file records the local changes in this fork relative to the original
`ccolon/disrupt-sc` repository. The upstream model changes are already part of
`upstream/main`; this file documents only the additional Norway compatibility
patches maintained here. Features merged from upstream are intentionally not
duplicated in this file.

## Comparison point

- Upstream: `https://github.com/ccolon/disrupt-sc`
- Fork: `https://github.com/francis-barre/disrupt-sc`
- Upstream baseline: `18e8e31` (`upstream/main`, 2026-09-21)

To reproduce the comparison:

```bash
git fetch upstream
git diff upstream/main main
git log --no-merges --oneline upstream/main..main
```

## Norway-specific compatibility changes

### Virtual firms

`Firm` now carries the spatial `virtual` flag, and `create_firms` propagates
it from the firm table. A virtual receiver bypasses the transport lookup when
receiving products, just as a virtual supplier already did. This is required
for Norway's offshore virtual oil-and-gas firm, whose flows are configured to
bypass the transport network.

### Sector-resolved country import density

When import rows are sector-resolved, country import density uses the selling
sector from the MRIO column. Import value and tonnage are included only when a
positive USD-per-ton density exists. This prevents service or otherwise
non-tonnage rows from distorting the effective goods density used for country
imports.

### Edge-specific road speeds

When road speed settings specify an edge attribute such as `max_speed`, a
positive numeric value on the edge is now used directly. Edges without a valid
positive value continue to use the configured road default. This allows the
Norway transport extraction's speed attributes to affect route costs.

### Calibration link output

`link_data.parquet` now includes `transport_modes`, serialized as a deterministic
`+`-separated list. The baseline link table produced by the upstream
initial-state export can therefore be consumed by the Norway calibration
workflow with the required route-mode information.

The high-volume `link_data` and `inventory_data` exports are now written as
batched Parquet files by default. The other small time-series exports remain
CSV. This keeps the row-wise writer interface and bounds memory use while
making the Norway calibration outputs substantially smaller and faster to
write. Readers retain CSV fallback for older runs.

The previously considered spatial `sector_type` and firm-level `usd_per_ton`
preservation branches are intentionally not included: the current Norway
inputs already provide the needed sector table and sector-level density table.

### Reading Norway edge capacities

The upstream capacity redesign uses named entries in
`transport_capacity_overrides` and ignores capacity columns carried by a
transport GeoPackage. Norway's extracted road and rail layers already contain
edge-specific daily capacities, so this fork adds the opt-in
`transport_capacity_from_edges` switch. It preserves those source capacities
and converts them from tons per day to tons per model step. The switch is
`False` by default and is enabled only by the Norway scope; it has no effect on
other scopes. `capacity_constraint` remains disabled for the current Norway
run, so preserving the capacities does not impose capacity rationing until a
Norway experiment explicitly enables it.

The upstream `per_sector_import_links` and optional country `usd_per_ton`
override are used as provided. Norway enables the former. Its country spatial
data has no `usd_per_ton` values, so the latter falls back to the calculated
sector/value density and does not override Norway's calibration.

### Foreign trade points are route endpoints only

Country OD points may be route origins or destinations, but not intermediate
nodes. Initial routing splits each marked point into a start and end copy in
the batched shortest-path graph; this avoids per-route fallback searches while
preserving normal edge costs. Disruption-time route searches apply the same
endpoint rule. No mode penalties or Norway-specific network changes are added.

The logistic-route cache build version is 6, so existing routes are rebuilt
once while the transport-network and supply-chain caches remain reusable.
On the Norway cache, 43,108 of 410,580 route assignments changed; none then
used a foreign point in transit, and none became unreachable. Route setup rose
from 93.1 to 101.3 seconds (+8.8%).

## Change history

| Commit | Change |
| --- | --- |
| `70ebd67` | Support Norway virtual firms and calibration outputs |
| `32baf27` | Export edge tons by cargo and flow category for Norway calibration |
| `0111d81` | Merge upstream capacity, transit, density, and sector-import features while preserving Norway compatibility |

## Maintenance rule

Update this file whenever a local fork-specific code or data contract changes.
Do not duplicate upstream features here; update the upstream baseline above
when the branch is rebased onto a newer upstream commit.

## Optional sparse import supplier links

`sparse_imports` is an opt-in supply-chain build setting. It defaults to
`false`, leaving the existing dense/aggregated import model unchanged. When
`true`, it sparsifies buyer links before normal supply-chain wiring. Seller
granularity remains controlled independently by `per_sector_import_links`.

The allocator starts from each buyer's existing positive import suppliers,
after the configured import-distance localization. For each import product,
it balances buyer requirements against partner-product totals, then uses
seeded 2x2 transportation-cycle pivots to remove redundant links without
changing
those margins. Firms' requirements and supplier totals are weighted by firm
importance; household totals are unweighted. The target average is configured
by `nb_import_suppliers_per_input` (default `1.5`), not a hard cap: products
with insufficient shared support can remain above it. No new partner links are
invented, and the allocator uses a local RNG so it does not change the dense
model's seeded supplier draws.

Set `sparse_imports: true` in a scope YAML file to enable it. A configured
`seed` makes the selection reproducible. The setting is included in run
provenance and the supply-chain cache fingerprint; changing it
rebuilds the supply-chain stage. The implementation
is isolated in
`src/disruptsc/init_pipeline/sparse_imports.py` to keep the upstream integration
small.

Validation: `tests/test_sparse_imports.py` checks default-off behavior,
reproducibility, margin conservation, and preservation of domestic inputs.
