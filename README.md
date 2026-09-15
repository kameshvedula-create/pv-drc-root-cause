# PV DRC Repair Agent

An explainable, closed-loop agent for identifying the likely root cause of a DRC violation, proposing bounded repairs, validating each repair, and rolling back regressions.

The current milestone is a tool-independent reference implementation. It includes deterministic policy checks, confidence-based abstention, ranked repair attempts, rollback, episode memory, and unit tests. OpenROAD/KLayout adapters can implement the small `DRCTool` protocol without changing the agent.

## Safety contract

A repair is committed only when validation shows the target was removed, the total violation count decreased, no new violation signature appeared, and no protected object was modified. Otherwise the agent rolls the attempt back. Low-confidence diagnoses abstain without editing the design.

## Quick start

```bash
python -m pip install -e ".[klayout]"
python -m unittest discover -s tests -v
python -m pvdrc_agent.demo
```

Python 3.10 or newer is required. The package has no third-party runtime dependencies.

## Agent loop

1. Inspect a normalized `ViolationCase`.
2. Predict a root cause with calibrated confidence.
3. Abstain below the configured confidence threshold.
4. Generate and rank bounded `RepairCandidate` objects.
5. Snapshot the design and apply one repair.
6. Run deterministic incremental DRC.
7. Commit only a strict improvement; otherwise roll back.
8. Record the episode for future retrieval and training.

## Integration status

Implement `DRCTool` adapters for KLayout report databases and OpenROAD database edits, then convert real SKY130 metal-spacing markers into `ViolationCase` records.


### KLayout report ingestion

```bash
python -m pvdrc_agent.klayout_report violations.lyrdb rule_layers.json > cases.jsonl
```

`rule_layers.json` maps exact KLayout category paths to layer names, for example
`{"met1_spacing": "met1"}`. This example category is illustrative; use the actual
category paths emitted by your chosen SKY130 deck. Category paths with punctuation
may be quoted by KLayout. No rule thresholds are guessed or embedded.

The parser reads boxes, polygons, edges, edge pairs and paths, keeps duplicate
markers distinct, and assigns order-independent geometry signatures. Coordinates
are in micrometres. Only flat top-cell reports are accepted; hierarchical markers
fail rather than being assigned incorrect placement coordinates. Missing layer
mappings and unsupported geometry fail explicitly. Full geometry is used for
identity, so geometric changes conservatively count as new violations.

### OpenROAD adapter

`OpenROADAdapter` implements `DRCTool`. Construct it with a route-ready ODB,
a scratch work directory, a trusted validation command argv, rule-to-layer mapping,
and a mandatory design guard callback. Then pass it to `DRCRepairAgent` with your
model and planner. The first supported action is:

```python
RepairCandidate("route-1", "detailed_route", {"iterations": 3, "seed": 0})
```

The adapter runs `read_db`, iteration-limited `detailed_route`, and `write_db`
in an isolated transaction. This is whole-design routing, not local marker repair.
Each candidate starts from the unchanged original. Successful candidates replace
the original ODB atomically; failures delete the candidate. Use one owner/process
per ODB. Concurrent edits are detected before commit, but this is not a lock service.

The validation command receives `PV_DRC_ODB` and `PV_DRC_REPORT`. It must export
that exact ODB through your technology-specific DEF/LEF-to-GDS flow (including
macro/standard-cell GDS), run the same full KLayout deck and write a fresh flat RDB.
It must return nonzero for incomplete runs. Empty, successfully completed RDBs
represent zero violations; missing output is never considered clean. A fresh
baseline is checked on every attempt to avoid accepting stale geometry.

The guard callback `(before_odb, after_odb, case)` must raise on connectivity,
protected-object or timing/QoR regressions. It is intentionally required: DRC alone
does not establish electrical correctness. Production integrations must implement
this guard with their actual netlist and timing checks; a no-op guard is for tests
only. Validation and guard configuration must remain fixed for a run.

### Validation and limits

Tests generate and reload real reports using KLayout 0.30.12. OpenROAD process
execution is simulated in transaction tests, including timeout, missing-report,
new-marker rollback and successful commit. No real SKY130 closure rate or speedup
has been measured. OpenROAD, a route-ready SKY130 ODB, the deck and export/guard
configuration are still required for a complete physical-design run. The existing
demo diagnoser is a stub, not a trained classifier.

API references: [KLayout report values](https://www.klayout.de/doc/code/class_RdbItemValue.html),
[OpenROAD detailed routing](https://github.com/The-OpenROAD-Project/OpenROAD/blob/master/src/drt/README.md).
