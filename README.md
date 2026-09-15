# PV DRC Repair Agent

An explainable, closed-loop agent for identifying the likely root cause of a DRC violation, proposing bounded repairs, validating each repair, and rolling back regressions.

The current milestone is a tool-independent reference implementation. It includes deterministic policy checks, confidence-based abstention, ranked repair attempts, rollback, episode memory, and unit tests. OpenROAD/KLayout adapters can implement the small `DRCTool` protocol without changing the agent.

## Safety contract

A repair is committed only when validation shows the target was removed, the total violation count decreased, no new violation signature appeared, and no protected object was modified. Otherwise the agent rolls the attempt back. Low-confidence diagnoses abstain without editing the design.

## Quick start

```bash
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

## Next integration

Implement `DRCTool` adapters for KLayout report databases and OpenROAD database edits, then convert real SKY130 metal-spacing markers into `ViolationCase` records.
