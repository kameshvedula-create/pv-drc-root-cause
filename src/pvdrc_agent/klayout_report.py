"""Parse flat/top-cell KLayout RDB reports; coordinates are micrometres."""
import hashlib
import json
from collections import Counter
from .models import ViolationCase


def parse_report(path, rule_layers):
    import klayout.rdb as rdb
    report = rdb.ReportDatabase()
    report.load(str(path))
    occurrences = Counter()
    cases = []
    for item in report.each_item():
        category = report.category_by_id(item.category_id())
        # Explicit mapping avoids guessing layers from arbitrary deck category names.
        rule = category.path()
        if rule not in rule_layers:
            raise ValueError(f"Missing rule/layer mapping: {rule}")
        cell = report.cell_by_id(item.cell_id()).name()
        if cell != report.top_cell_name:
            raise ValueError("Hierarchical markers require transforms; export a flat top-cell report")
        boxes, geometry = [], []
        for value in item.each_value():
            for kind in ('box', 'polygon', 'edge', 'edge_pair', 'path'):
                if getattr(value, 'is_' + kind)():
                    shape = getattr(value, kind)()
                    boxes.append(shape if kind == 'box' else shape.bbox())
                    geometry.append(value.to_s())
                    break
        if not boxes:
            raise ValueError(f"Marker has no supported geometry: {rule}")
        bbox = (min(b.left for b in boxes), min(b.bottom for b in boxes),
                max(b.right for b in boxes), max(b.top for b in boxes))
        identity = json.dumps([rule, cell, sorted(geometry)], separators=(',', ':'))
        signature = hashlib.sha256(identity.encode()).hexdigest()
        occurrences[signature] += 1
        # Duplicate markers must count separately; report order must not alter identities.
        marker_id = f'{signature}:{occurrences[signature]}'
        cases.append(ViolationCase(marker_id, rule, rule_layers[rule], bbox,
                                   {'cell': cell, 'units': 'um'}))
    return cases


def main():
    import argparse
    from dataclasses import asdict
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report')
    parser.add_argument('rule_layers', help='JSON object mapping exact category paths to layers')
    args = parser.parse_args()
    with open(args.rule_layers) as stream:
        layers = json.load(stream)
    for case in parse_report(args.report, layers):
        data = asdict(case)
        data['protected_objects'] = sorted(case.protected_objects)
        print(json.dumps(data))


if __name__ == '__main__':
    main()
