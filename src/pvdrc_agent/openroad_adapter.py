"""Single-owner ODB transaction adapter with fresh external KLayout validation."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from .klayout_report import parse_report
from .models import ValidationReport


class OpenROADAdapter:
    def __init__(self, odb, workdir, validate_command, rule_layers, guard,
                 executable='openroad', timeout=300):
        """guard(before_odb, after_odb, case) must raise on connectivity/QoR/protection failure.

        validate_command is a trusted argv sequence. It receives PV_DRC_ODB and
        PV_DRC_REPORT environment paths and must export the ODB to layout, run
        the same full KLayout deck, and write a flat RDB. Never feed model text
        to this command or to a Tcl interpreter.
        """
        if not validate_command or not callable(guard):
            raise ValueError('A validation command and design guard are required')
        self.odb = Path(odb).resolve()
        self.root = Path(workdir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.validate_command = list(validate_command)
        self.rule_layers, self.guard = dict(rule_layers), guard
        self.executable, self.timeout = executable, timeout
        self.transaction = None
        self.validated = False

    def _report(self, odb, case):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            output = Path(directory) / 'report.lyrdb'
            env = dict(os.environ, PV_DRC_ODB=str(odb), PV_DRC_REPORT=str(output))
            subprocess.run(self.validate_command, env=env, cwd=directory,
                           check=True, timeout=self.timeout, capture_output=True)
            if not output.is_file():
                raise RuntimeError('Validator produced no fresh report')
            markers = parse_report(output, self.rule_layers)
            ids = frozenset(m.violation_id for m in markers)
            return ValidationReport(ids, case.violation_id in ids)

    def inspect(self, case):
        if self.transaction is not None:
            raise RuntimeError('Transaction already active')
        return self._report(self.odb, case)

    def snapshot(self):
        if self.transaction is not None:
            raise RuntimeError('Transaction already active')
        directory = Path(tempfile.mkdtemp(dir=self.root))
        shutil.copy2(self.odb, directory / 'before.odb')
        self.transaction = directory
        self.validated = False
        return directory

    def apply(self, repair):
        if self.transaction is None:
            raise RuntimeError('Snapshot required')
        self.validated = False
        if repair.action != 'detailed_route' or set(repair.parameters) - {'iterations', 'seed'}:
            raise ValueError('Only bounded detailed_route is supported')
        iterations = repair.parameters.get('iterations', 3)
        seed = repair.parameters.get('seed', 0)
        if type(iterations) is not int or not 1 <= iterations <= 64:
            raise ValueError('iterations must be an integer from 1 to 64')
        if type(seed) is not int or not 0 <= seed <= 2147483647:
            raise ValueError('seed must be a nonnegative 32-bit integer')
        directory = self.transaction
        (directory / 'candidate.odb').unlink(missing_ok=True)
        # Fixed relative filenames avoid Tcl interpolation of untrusted paths.
        script = ('read_db before.odb\n'
                  f'detailed_route -droute_end_iter {iterations} -or_seed {seed}\n'
                  'write_db candidate.odb\n')
        (directory / 'repair.tcl').write_text(script)
        subprocess.run([self.executable, '-exit', 'repair.tcl'], cwd=directory,
                       check=True, timeout=self.timeout, capture_output=True)
        if not (directory / 'candidate.odb').is_file():
            raise RuntimeError('OpenROAD produced no candidate database')

    def validate(self, case):
        directory = self.transaction
        if directory is None:
            raise RuntimeError('Snapshot required')
        candidate = directory / 'candidate.odb'
        self.guard(directory / 'before.odb', candidate, case)
        report = self._report(candidate, case)
        from .policy import validation_is_safe
        before = self._report(directory / 'before.odb', case)
        self.validated = validation_is_safe(before, report)[0]
        return report

    def commit(self, snapshot):
        if snapshot != self.transaction or not self.validated:
            raise RuntimeError('Validated transaction required')
        if self.odb.read_bytes() != (snapshot / 'before.odb').read_bytes():
            raise RuntimeError('Original database changed during transaction')
        # Stage alongside destination for same-filesystem atomic replacement.
        fd, name = tempfile.mkstemp(dir=self.odb.parent)
        os.close(fd)
        try:
            shutil.copy2(snapshot / 'candidate.odb', name)
            os.replace(name, self.odb)
        finally:
            Path(name).unlink(missing_ok=True)
        self.rollback(snapshot)

    def rollback(self, snapshot):
        if snapshot != self.transaction:
            raise RuntimeError('Invalid transaction token')
        shutil.rmtree(snapshot)
        self.transaction = None
        self.validated = False
