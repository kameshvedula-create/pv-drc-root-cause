from .interfaces import DRCTool, Diagnoser, EpisodeStore, RepairPlanner
from .models import AgentConfig, AgentResult, RepairCandidate, ViolationCase
from .policy import repair_is_allowed, validation_is_safe


class DRCRepairAgent:
    """Orchestrates diagnosis, bounded repair, validation, and rollback."""

    def __init__(self, diagnoser: Diagnoser, planner: RepairPlanner, tool: DRCTool, memory: EpisodeStore, config: AgentConfig | None = None) -> None:
        self.diagnoser = diagnoser
        self.planner = planner
        self.tool = tool
        self.memory = memory
        self.config = config or AgentConfig()

    def run(self, case: ViolationCase) -> AgentResult:
        diagnosis = self.diagnoser.diagnose(case)
        before = self.tool.inspect(case)
        if diagnosis.confidence < self.config.confidence_threshold:
            result = AgentResult("abstained", case.violation_id, diagnosis, reason="diagnosis confidence below threshold", before_count=before.total_violations, after_count=before.total_violations)
            self._record(case, result)
            return result

        candidates = sorted(self.planner.propose(case, diagnosis), key=self._candidate_score, reverse=True)[:self.config.max_attempts]
        attempts = 0
        last_reason = "no repair candidates"
        for repair in candidates:
            allowed, reason = repair_is_allowed(case, repair)
            if not allowed:
                last_reason = reason
                continue
            attempts += 1
            snapshot = self.tool.snapshot()
            try:
                self.tool.apply(repair)
                after = self.tool.validate(case)
                safe, reason = validation_is_safe(before, after)
                if safe:
                    self.tool.commit(snapshot)
                    result = AgentResult("fixed", case.violation_id, diagnosis, repair, attempts, before_count=before.total_violations, after_count=after.total_violations)
                    self._record(case, result)
                    return result
                last_reason = reason
            except Exception as exc:
                last_reason = f"tool failure: {type(exc).__name__}"
            self.tool.rollback(snapshot)

        result = AgentResult("unresolved", case.violation_id, diagnosis, attempts=attempts, reason=last_reason, before_count=before.total_violations, after_count=before.total_violations)
        self._record(case, result)
        return result

    @staticmethod
    def _candidate_score(repair: RepairCandidate) -> float:
        return -(0.5 * repair.edit_cost + 2.0 * repair.risk)

    def _record(self, case: ViolationCase, result: AgentResult) -> None:
        self.memory.record({"violation_id": case.violation_id, "rule_id": case.rule_id, "status": result.status, "root_cause": result.diagnosis.root_cause.value, "confidence": result.diagnosis.confidence, "repair_id": result.chosen_repair.repair_id if result.chosen_repair else None, "attempts": result.attempts, "reason": result.reason, "before_count": result.before_count, "after_count": result.after_count})
