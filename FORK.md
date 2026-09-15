# Fork changes

This file records the local changes in this fork relative to the original
`ccolon/disrupt-sc` repository. The upstream model changes are already part of
`upstream/main`; this file documents only the additional Norway compatibility
patch maintained here.

## Comparison point

- Upstream: `https://github.com/ccolon/disrupt-sc`
- Fork: `https://github.com/francis-barre/disrupt-sc`
- Upstream baseline: `6707ea2` (`upstream/main`, 2026-09-15)

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

`link_data.csv` now includes `transport_modes`, serialized as a deterministic
`+`-separated list. The baseline link table produced by the upstream
initial-state export can therefore be consumed by the Norway calibration
workflow with the required route-mode information.

The previously considered spatial `sector_type` and firm-level `usd_per_ton`
preservation branches are intentionally not included: the current Norway
inputs already provide the needed sector table and sector-level density table.

## Change history

| Commit | Change |
| --- | --- |
| `70ebd67` | Support Norway virtual firms and calibration outputs |

## Maintenance rule

Update this file whenever a local fork-specific code or data contract changes.
Do not duplicate upstream features here; update the upstream baseline above
when the branch is rebased onto a newer upstream commit.
