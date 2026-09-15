from .agent import DRCRepairAgent
from .memory import InMemoryEpisodeStore
from .models import Diagnosis, RepairCandidate, RootCause, ValidationReport, ViolationCase


class DemoDiagnoser:
    def diagnose(self, case): return Diagnosis(RootCause.SHORT_JOG, 0.91, ("small jog length", "parallel neighbor"))


class DemoPlanner:
    def propose(self, case, diagnosis): return [RepairCandidate("remove-jog", "remove_short_jog", edit_cost=1, risk=0.1)]


class DemoTool:
    def __init__(self): self.fixed = False
    def inspect(self, case): return ValidationReport(frozenset({case.violation_id, "M1.W.1:9"}), True)
    def snapshot(self): return self.fixed
    def apply(self, repair): self.fixed = True
    def validate(self, case): return ValidationReport(frozenset({"M1.W.1:9"}), not self.fixed)
    def commit(self, snapshot): pass
    def rollback(self, snapshot): self.fixed = snapshot


def main():
    case = ViolationCase("M1.S.1:42", "M1.S.1", "met1", (0.0, 0.0, 1.0, 1.0))
    print(DRCRepairAgent(DemoDiagnoser(), DemoPlanner(), DemoTool(), InMemoryEpisodeStore()).run(case))


if __name__ == "__main__": main()
