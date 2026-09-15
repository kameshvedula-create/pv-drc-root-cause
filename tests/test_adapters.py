import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import klayout.db as db
import klayout.rdb as rdb
from pvdrc_agent.klayout_report import parse_report
from pvdrc_agent.openroad_adapter import OpenROADAdapter
from pvdrc_agent import DRCRepairAgent, RepairCandidate
from pvdrc_agent.memory import InMemoryEpisodeStore
from test_agent import StubDiagnoser, StubPlanner


def report(path, boxes, cell='top'):
    r = rdb.ReportDatabase()
    r.top_cell_name = 'top'
    c = r.create_cell(cell)
    k = r.create_category('met1_spacing')
    for box in boxes:
        r.create_item(c.rdb_id(), k.rdb_id()).add_value(box)
    r.save(str(path))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mapping = {'met1_spacing': 'met1'}
        self.box = db.DBox(0.1, 0.2, 0.3, 0.4)
        self.input = self.root / 'input.lyrdb'
        report(self.input, [self.box])
        self.case = parse_report(self.input, self.mapping)[0]
        self.odb = self.root / 'design.odb'
        self.odb.write_bytes(b'before')

    def test_real_rdb_roundtrip_and_duplicates(self):
        report(self.input, [self.box, self.box])
        cases = parse_report(self.input, self.mapping)
        self.assertEqual(2, len({c.violation_id for c in cases}))
        for expected, actual in zip((0.1, 0.2, 0.3, 0.4), cases[0].bbox):
            self.assertAlmostEqual(expected, actual)
        self.assertEqual(self.case.violation_id, cases[0].violation_id)

    def test_reordering_stable(self):
        other = db.DBox(1, 1, 2, 2)
        report(self.input, [self.box, other])
        first = {c.violation_id for c in parse_report(self.input, self.mapping)}
        report(self.input, [other, self.box])
        self.assertEqual(first, {c.violation_id for c in parse_report(self.input, self.mapping)})

    def test_missing_mapping_and_hierarchy_fail_closed(self):
        with self.assertRaises(ValueError): parse_report(self.input, {})
        report(self.input, [self.box], 'child')
        with self.assertRaises(ValueError): parse_report(self.input, self.mapping)

    def test_edge_pair(self):
        shape = db.DEdgePair(db.DEdge(0, 0, 1, 0), db.DEdge(0, 0.1, 1, 0.1))
        report(self.input, [shape])
        self.assertEqual((0, 0, 1, 0.1), parse_report(self.input, self.mapping)[0].bbox)

    def run_agent(self, bad=False, missing=False, fail=False):
        def process(argv, **kw):
            if argv[0] == 'openroad':
                if fail: raise subprocess.TimeoutExpired(argv, 1)
                directory = Path(kw['cwd'])
                self.assertIn('detailed_route -droute_end_iter 3 -or_seed 0',
                              (directory / 'repair.tcl').read_text())
                (directory / 'candidate.odb').write_bytes(b'after')
            else:
                env = kw['env']
                before = Path(env['PV_DRC_ODB']).read_bytes() == b'before'
                if missing and not before: return
                boxes = [self.box] if before else ([db.DBox(2, 2, 3, 3)] if bad else [])
                report(env['PV_DRC_REPORT'], boxes)
        tool = OpenROADAdapter(self.odb, self.root / 'work', ['validator'], self.mapping,
                               lambda before, after, case: None)
        agent = DRCRepairAgent(StubDiagnoser(), StubPlanner([
            RepairCandidate('route', 'detailed_route')]), tool, InMemoryEpisodeStore())
        with patch('pvdrc_agent.openroad_adapter.subprocess.run', side_effect=process):
            result = agent.run(self.case)
        self.assertIsNone(tool.transaction)
        return result

    def test_agent_transaction_commit(self):
        self.assertEqual('fixed', self.run_agent().status)
        self.assertEqual(b'after', self.odb.read_bytes())

    def test_regression_rollback(self):
        self.assertEqual('unresolved', self.run_agent(bad=True).status)
        self.assertEqual(b'before', self.odb.read_bytes())

    def test_missing_report_rollback(self):
        self.assertEqual('unresolved', self.run_agent(missing=True).status)
        self.assertEqual(b'before', self.odb.read_bytes())

    def test_timeout_rollback(self):
        self.assertEqual('unresolved', self.run_agent(fail=True).status)
        self.assertEqual(b'before', self.odb.read_bytes())

    def test_reject_tcl_injection_and_unvalidated_commit(self):
        tool = OpenROADAdapter(self.odb, self.root / 'work', ['validator'], self.mapping,
                               lambda *args: None)
        token = tool.snapshot()
        with self.assertRaises(ValueError):
            tool.apply(RepairCandidate('bad', 'detailed_route', {'seed': '0; exit'}))
        with self.assertRaises(RuntimeError): tool.commit(token)
        tool.rollback(token)
