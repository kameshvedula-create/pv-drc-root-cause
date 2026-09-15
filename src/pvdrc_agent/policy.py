from .models import RepairCandidate, ValidationReport, ViolationCase


def repair_is_allowed(case: ViolationCase, repair: RepairCandidate) -> tuple[bool, str]:
    overlap = case.protected_objects & repair.touched_objects
    if overlap:
        return False, f"repair touches protected objects: {', '.join(sorted(overlap))}"
    return True, ""


def validation_is_safe(before: ValidationReport, after: ValidationReport) -> tuple[bool, str]:
    if after.protected_objects_modified:
        return False, "validation detected modifications to protected objects"
    if after.target_present:
        return False, "target violation remains"
    if after.violation_signatures - before.violation_signatures:
        return False, "repair introduced new violation signatures"
    if after.total_violations >= before.total_violations:
        return False, "total violation count did not decrease"
    return True, ""
