"""L4: Recompute all frozen R3 summary fields from CSV; no search or AC solve."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / 'results/frozen'
TEXT_FIELDS = {'case', 'method', 'cohort', 'job_id', 'input_sha256', 'status', 'path', 'support_nodes', 'provenance', 'error_message'}
BOOL_FIELDS = {'feasible_witness', 'method_exact_certificate', 'known_feasible', 'no_witness_on_known_feasible', 'completed_miss_on_known_feasible'}


def read_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def parse(row):
    output = {}
    for key, value in row.items():
        if key in TEXT_FIELDS:
            output[key] = value
        elif key in BOOL_FIELDS:
            if value not in {'True', 'False'}:
                raise ValueError(f'Invalid boolean in {key}')
            output[key] = value == 'True'
        else:
            output[key] = None if value in {'NA', ''} else float(value)
    return output


def summarize(rows):
    summaries = []
    keys = sorted({('large_extension' if r['cohort'] == 'large_extension' else 'small_medium', r['method']) for r in rows})
    for cohort, method in keys:
        group = [r for r in rows if r['method'] == method and (r['cohort'] == 'large_extension') == (cohort == 'large_extension')]
        status = Counter(r['status'] for r in group)
        gaps = [r['optimality_gap_percent'] for r in group if r['optimality_gap_percent'] is not None]
        best = [r['best_known_gap_percent'] for r in group if r['best_known_gap_percent'] is not None]
        known = sum(r['known_feasible'] for r in group)
        misses = sum(r['no_witness_on_known_feasible'] for r in group)
        completed = sum(r['completed_miss_on_known_feasible'] for r in group)
        feasible = sum(r['feasible_witness'] for r in group)
        out = dict(cohort=cohort, method=method, records=len(group), feasible_witnesses=feasible,
                   feasible_fraction=feasible/len(group), known_feasible_instances=known,
                   known_feasible_misses=misses, known_feasible_miss_fraction=misses/known if known else None,
                   completed_misses=completed, limited_or_error_misses=misses-completed,
                   optimality_gap_count=len(gaps), max_optimality_gap_percent=max(gaps) if gaps else None,
                   max_best_known_gap_percent=max(best) if best else None,
                   certified_feasible=sum(r['method_exact_certificate'] and r['feasible_witness'] for r in group),
                   timeout=status['TIMEOUT'], resource_limit=status['RESOURCE_LIMIT'], error=status['ERROR'],
                   new_r3_rows=sum(r['provenance']=='NEW_R3' for r in group),
                   reused_historical_rows=sum(r['provenance']=='REUSED_HISTORICAL' for r in group))
        for metric in ('runtime_ms', 'labels_generated', 'labels_expanded', 'labels_pruned', 'max_active_labels', 'peak_process_working_set_bytes'):
            values = [r[metric] for r in group if r[metric] is not None]
            out[metric+'_median'] = median(values) if values else None
            out[metric+'_max'] = max(values) if values else None
            out[metric+'_available'] = len(values)
        summaries.append(out)
    return summaries


def validate_rows(rows):
    if len(rows) != 249 or len({r['job_id'] for r in rows}) != 249:
        raise ValueError('Frozen panel must contain 249 distinct primary method rows')
    if sum(r['cohort']=='large_extension' for r in rows) != 9:
        raise ValueError('Frozen large panel must contain nine records')
    for row in rows:
        if row['certified_optimum'] is None and row['optimality_gap_percent'] is not None:
            raise ValueError('Unknown optimality must remain NA')
        if not row['feasible_witness'] and row['objective'] is not None:
            raise ValueError('Unavailable witness cannot have an objective')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', default='outputs/reaggregation')
    args=parser.parse_args()
    output=(ROOT/args.output).resolve();output.relative_to(ROOT)
    rows=[parse(r) for r in read_rows(FROZEN/'GRAPH_PRIMARY_RECORDS.csv')]
    validate_rows(rows)
    actual=summarize(rows)
    by_key={(r['cohort'],r['method']):r for r in actual}
    checks=[]
    for expected in read_rows(FROZEN/'GRAPH_METHOD_SUMMARY.csv'):
        current=by_key[(expected['cohort'],expected['method'])]
        for field, value in expected.items():
            got=current[field]
            ok=(got==value) if field in {'cohort','method'} else (got is None if value=='NA' else got is not None and math.isclose(float(value),got,rel_tol=1e-12,abs_tol=1e-12))
            checks.append(dict(cohort=expected['cohort'],method=expected['method'],field=field,status='PASS' if ok else 'FAIL',expected=value,actual=got))
    limits=read_rows(FROZEN/'GRAPH_LIMITED_AND_FAILED.csv')
    observed={r['job_id'] for r in rows if r['status'] in {'RESOURCE_LIMIT','TIMEOUT','ERROR'}}
    if observed != {r['job_id'] for r in limits} or len(limits)!=7:
        raise ValueError('Saved limited/failed outcomes differ from primary rows')
    failures=[r for r in checks if r['status']=='FAIL']
    report=dict(status='FAIL' if failures else 'PASS',primary_records=len(rows),summary_rows=len(actual),
                checked_summary_cells=len(checks),passed=len(checks)-len(failures),failed=len(failures),
                retained_limited_records=len(limits),new_searches=0,new_ac_solves=0,
                source_csv_sha256=hashlib.sha256((FROZEN/'GRAPH_PRIMARY_RECORDS.csv').read_bytes()).hexdigest(),checks=checks)
    output.mkdir(parents=True,exist_ok=True)
    (output/'verification.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    fields=list(actual[0])
    with (output/'GRAPH_METHOD_SUMMARY.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        writer.writerows({k:'NA' if v is None else v for k,v in row.items()} for row in actual)
    print(json.dumps({k:v for k,v in report.items() if k!='checks'}))
    return 1 if failures else 0


if __name__=='__main__':
    raise SystemExit(main())
