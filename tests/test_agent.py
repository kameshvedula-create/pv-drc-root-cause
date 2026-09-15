import unittest
from pvdrc_agent import AgentConfig, DRCRepairAgent, Diagnosis, RepairCandidate, RootCause, ValidationReport, ViolationCase
from pvdrc_agent.memory import InMemoryEpisodeStore


class StubDiagnoser:
    def __init__(self, confidence=0.9): self.confidence = confidence
    def diagnose(self, case): return Diagnosis(RootCause.SHORT_JOG, self.confidence)


class StubPlanner:
    def __init__(self, candidates): self.candidates = candidates
    def propose(self, case, diagnosis): return self.candidates


class ScriptedTool:
    def __init__(self, reports):
        self.reports, self.state, self.rollbacks, self.commits = iter(reports), [], 0, 0
    def inspect(self, case): return next(self.reports)
    def snapshot(self): return list(self.state)
    def apply(self, repair): self.state.append(repair.repair_id)
    def validate(self, case): return next(self.reports)
    def commit(self, snapshot): self.commits += 1
    def rollback(self, snapshot): self.state, self.rollbacks = snapshot, self.rollbacks + 1


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.case = ViolationCase("target", "M1.S.1", "met1", (0, 0, 1, 1))
        self.repair = RepairCandidate("r1", "move_wire", edit_cost=1, risk=0.1)
        self.before = ValidationReport(frozenset({"target", "existing"}), True)

    def agent(self, tool, confidence=0.9, candidates=None, case=None):
        memory = InMemoryEpisodeStore()
        agent = DRCRepairAgent(StubDiagnoser(confidence), StubPlanner(candidates if candidates is not None else [self.repair]), tool, memory, AgentConfig(0.7, 3))
        return agent, memory, case or self.case

    def test_commits_strict_improvement(self):
        tool = ScriptedTool([self.before, ValidationReport(frozenset({"existing"}), False)])
        agent, memory, case = self.agent(tool)
        result = agent.run(case)
        self.assertEqual("fixed", result.status)
        self.assertEqual((1, 0), (tool.commits, tool.rollbacks))
        self.assertEqual("fixed", memory.episodes[0]["status"])

    def test_abstains_without_editing(self):
        tool = ScriptedTool([self.before])
        agent, _, case = self.agent(tool, confidence=0.4)
        self.assertEqual("abstained", agent.run(case).status)
        self.assertEqual([], tool.state)

    def test_rolls_back_new_violation(self):
        tool = ScriptedTool([self.before, ValidationReport(frozenset({"existing", "new-rule"}), False)])
        agent, _, case = self.agent(tool)
        self.assertEqual("unresolved", agent.run(case).status)
        self.assertEqual((1, []), (tool.rollbacks, tool.state))

    def test_skips_protected_object(self):
        case = ViolationCase("target", "M1.S.1", "met1", (0, 0, 1, 1), protected_objects=frozenset({"macro/A"}))
        repair = RepairCandidate("unsafe", "move_wire", touched_objects=frozenset({"macro/A"}))
        tool = ScriptedTool([self.before])
        agent, _, case = self.agent(tool, candidates=[repair], case=case)
        result = agent.run(case)
        self.assertEqual(("unresolved", 0, []), (result.status, result.attempts, tool.state))

    def test_rolls_back_when_target_remains(self):
        tool = ScriptedTool([self.before, ValidationReport(frozenset({"target", "existing"}), True)])
        agent, _, case = self.agent(tool)
        self.assertEqual("unresolved", agent.run(case).status)
        self.assertEqual(1, tool.rollbacks)


if __name__ == "__main__": unittest.main()
