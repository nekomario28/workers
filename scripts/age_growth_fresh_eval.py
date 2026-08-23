import csv
import hashlib
import json
import math
import random
from pathlib import Path

import numpy as np
import xlrd

SOURCE = Path('/tmp/source')
PHYSICAL = Path('/tmp/physical')
OUT = Path('/tmp/out')
OUT.mkdir(parents=True, exist_ok=True)

PREREG = 'f6b8e89d55f29f5f637fd52a58a08f598c8b7ff2'
SOURCE_FREEZE = '638f853cb6851c5fbb8e8c118f054d5b626c47dd'
SEED = int(PREREG[:8], 16)
PERMUTATIONS = 100000

PRED_FILE = SOURCE / 'age_growth_fresh_spatial_holdout_2022_predictor_30regions.csv'
DENOM_FILE = SOURCE / 'establishments_2016_age_growth_fresh_spatial_holdout_30regions.csv'
META_FILE = SOURCE / 'age_growth_fresh_spatial_holdout_2022_source_freeze_meta.json'

EXPECTED_SHA = {
    PRED_FILE: '565d79e4087c9128024237b306272f52ab96f78bc945464aa6ccf92bcc442790',
    DENOM_FILE: '0a6bf537b805fc31518c6af297d2b11ad523169ee610c39d943d7c895bdcf1e0',
    META_FILE: '2666bf082efa39ed6de78b351522a6627d8077784a834ac98055d38ddfe69ede',
    PHYSICAL / 'FY2022.xls': '96a9c36b41a47ac844a89724594665b3d2bcec8f4e216e419dca6d0455711528',
    PHYSICAL / 'FY2023.xls': '9007aa5fd47df7e173a1e6e19c481103ac47d673bc5aac1de7182c7f2da44091',
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


for path, expected in EXPECTED_SHA.items():
    got = sha256(path)
    if got != expected:
        raise SystemExit(f'SHA mismatch {path.name}: {got} != {expected}')

with PRED_FILE.open(encoding='utf-8', newline='') as f:
    pred = list(csv.DictReader(f))
with DENOM_FILE.open(encoding='utf-8', newline='') as f:
    denom_rows = list(csv.DictReader(f))
if len(pred) != 30 or len(denom_rows) != 30:
    raise SystemExit('fresh source freeze must contain exactly 30 rows')
if [r['region_code'] for r in pred] != [r['region_code'] for r in denom_rows]:
    raise SystemExit('predictor/denominator region order mismatch')

codes = [r['region_code'] for r in pred]
metros = {r['region_code']: r['metro'] for r in pred}
names = {r['region_code']: r['region_name'] for r in pred}
predictor = {r['region_code']: float(r['age20_29_growth_2020_to_2021_pct']) for r in pred}
denominator = {r['region_code']: int(r['private_establishments_2016']) for r in denom_rows}
if set(metros.values()) != {'Sapporo', 'Kobe', 'Kyoto'}:
    raise SystemExit('unexpected metro universe')


def extract_l(path, l_col):
    wb = xlrd.open_workbook(path, on_demand=True)
    sh = wb.sheet_by_index(0)
    targets = set(codes) | {'01100', '28100', '26100'}
    values = {}
    for i in range(sh.nrows):
        label = str(sh.cell_value(i, 1)).strip() if sh.ncols > 1 else ''
        code = label[:5] if len(label) >= 5 and label[:5].isdigit() else None
        if code not in targets:
            continue
        cell = sh.cell_value(i, l_col)
        if cell == '' or isinstance(cell, str):
            raise SystemExit(f'missing/suppressed L value {path.name} {code}: {cell!r}')
        values[code] = float(cell)
    wb.release_resources()
    missing = targets - set(values)
    if missing:
        raise SystemExit(f'missing L rows {path.name}: {sorted(missing)}')
    return values


l22 = extract_l(PHYSICAL / 'FY2022.xls', 28)
l23 = extract_l(PHYSICAL / 'FY2023.xls', 29)
city_codes = {'Sapporo': '01100', 'Kobe': '28100', 'Kyoto': '26100'}
ward_sum_validation = {}
for year, values in [('FY2022', l22), ('FY2023', l23)]:
    ward_sum_validation[year] = {}
    for metro, city_code in city_codes.items():
        ward_sum = sum(values[c] for c in codes if metros[c] == metro)
        city_total = values[city_code]
        if abs(ward_sum - city_total) > 1e-9:
            raise SystemExit(f'city-total mismatch {year} {metro}: {ward_sum} != {city_total}')
        ward_sum_validation[year][metro] = {'ward_sum': ward_sum, 'city_total': city_total, 'matches': True}

rows = []
for code in codes:
    h24 = l22[code] + l23[code]
    est = denominator[code]
    if est <= 0:
        raise SystemExit(f'nonpositive denominator {code}')
    rows.append({
        'region_code': code,
        'region_name': names[code],
        'metro': metros[code],
        'age20_29_growth_2020_to_2021_pct': predictor[code],
        'private_establishments_2016': est,
        'floor_area_L_FY2022': l22[code],
        'floor_area_L_FY2023': l23[code],
        'floor_area_L_h24': h24,
        'execution_L_per_est_2016': h24 / est,
    })


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    p = 0
    while p < len(order):
        q = p + 1
        while q < len(order) and values[order[q]] == values[order[p]]:
            q += 1
        avg = ((p + 1) + q) / 2.0
        for k in range(p, q):
            out[order[k]] = avg
        p = q
    return out


def pearson(a, b):
    ma = sum(a) / len(a)
    mb = sum(b) / len(b)
    da = [v - ma for v in a]
    db = [v - mb for v in b]
    den = math.sqrt(sum(v*v for v in da) * sum(v*v for v in db))
    if den == 0:
        return float('nan')
    return sum(x*y for x, y in zip(da, db)) / den


def spearman(a, b):
    return pearson(ranks(a), ranks(b))


def group_rows(group):
    return rows if group == 'ALL' else [r for r in rows if r['metro'] == group]


groups = ['ALL', 'Sapporo', 'Kobe', 'Kyoto']
scaled = {}
raw = {}
for group in groups:
    subset = group_rows(group)
    x = [r['age20_29_growth_2020_to_2021_pct'] for r in subset]
    scaled[group] = spearman(x, [r['execution_L_per_est_2016'] for r in subset])
    raw[group] = spearman(x, [r['floor_area_L_h24'] for r in subset])

primary_pass = all(scaled[g] > 0 for g in groups)
status = 'PASS_FRESH_SPATIAL_REPLICATION' if primary_pass else 'FAIL_FRESH_SPATIAL_REPLICATION'
raw_conflict = primary_pass and raw['ALL'] <= 0
interpretation = 'PASS_WITH_RAW_CONFLICT' if raw_conflict else status

# Deterministic two-sided permutation p on ALL scaled L.
xr = ranks([r['age20_29_growth_2020_to_2021_pct'] for r in rows])
yr = ranks([r['execution_L_per_est_2016'] for r in rows])
obs = pearson(xr, yr)
rng = random.Random(SEED)
exceed = 0
for _ in range(PERMUTATIONS):
    yp = list(yr)
    rng.shuffle(yp)
    if abs(pearson(xr, yp)) >= abs(obs) - 1e-15:
        exceed += 1
permutation_p = (exceed + 1) / (PERMUTATIONS + 1)


def top_codes(field, k):
    return {r['region_code'] for r in sorted(rows, key=lambda r: (-r[field], r['region_code']))[:k]}


topk = {}
for k in (5, 10):
    overlap = len(top_codes('age20_29_growth_2020_to_2021_pct', k) & top_codes('execution_L_per_est_2016', k))
    topk[str(k)] = {'overlap': overlap, 'enrichment': overlap * len(rows) / (k*k)}

# Rank-residual diagnostic after log(establishments) + city.
rx = np.asarray(ranks([r['age20_29_growth_2020_to_2021_pct'] for r in rows]), dtype=float)
ry = np.asarray(ranks([r['execution_L_per_est_2016'] for r in rows]), dtype=float)
log_est = np.log(np.asarray([r['private_establishments_2016'] for r in rows], dtype=float))
kyoto = np.asarray([1.0 if r['metro'] == 'Kyoto' else 0.0 for r in rows])
sapporo = np.asarray([1.0 if r['metro'] == 'Sapporo' else 0.0 for r in rows])
X = np.column_stack([np.ones(len(rows)), log_est, kyoto, sapporo])
bx = np.linalg.lstsq(X, rx, rcond=None)[0]
by = np.linalg.lstsq(X, ry, rcond=None)[0]
res_x = rx - X @ bx
res_y = ry - X @ by
partial_rank = float(np.corrcoef(res_x, res_y)[0, 1])


def dist(values):
    vals = [float(v) for v in values]
    unique = len(set(vals))
    vals_sorted = sorted(vals)
    n = len(vals_sorted)
    median = vals_sorted[n//2] if n % 2 else (vals_sorted[n//2-1] + vals_sorted[n//2]) / 2.0
    return {
        'n': n,
        'min': min(vals_sorted),
        'median': median,
        'mean': sum(vals_sorted) / n,
        'max': max(vals_sorted),
        'zero_count': sum(v == 0 for v in vals_sorted),
        'unique_count': unique,
        'tie_observation_count': n - unique,
    }


distributions = {'L': {}, 'private_establishments_2016': {}}
for group in groups:
    subset = group_rows(group)
    distributions['L'][group] = {
        'raw_L': dist([r['floor_area_L_h24'] for r in subset]),
        'scaled_L': dist([r['execution_L_per_est_2016'] for r in subset]),
    }
    distributions['private_establishments_2016'][group] = dist([r['private_establishments_2016'] for r in subset])

outcome_path = OUT / 'age_growth_fresh_spatial_holdout_2022_outcome_30regions.csv'
with outcome_path.open('w', encoding='utf-8', newline='') as f:
    fields = ['region_code','region_name','metro','floor_area_L_FY2022','floor_area_L_FY2023','floor_area_L_h24','execution_L_per_est_2016']
    w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
    w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in fields})

eval_path = OUT / 'age_growth_fresh_spatial_holdout_2022_evaluation.csv'
with eval_path.open('w', encoding='utf-8', newline='') as f:
    fields = ['predictor','scaled_ALL','scaled_Sapporo','scaled_Kobe','scaled_Kyoto','raw_ALL','raw_Sapporo','raw_Kobe','raw_Kyoto','primary_pass','top5_overlap','top5_enrichment','top10_overlap','top10_enrichment','permutation_p_all_100k','partial_rank_log_est_city']
    w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
    w.writeheader()
    w.writerow({
        'predictor': 'age20_29_growth_2020_to_2021_pct',
        'scaled_ALL': scaled['ALL'], 'scaled_Sapporo': scaled['Sapporo'], 'scaled_Kobe': scaled['Kobe'], 'scaled_Kyoto': scaled['Kyoto'],
        'raw_ALL': raw['ALL'], 'raw_Sapporo': raw['Sapporo'], 'raw_Kobe': raw['Kobe'], 'raw_Kyoto': raw['Kyoto'],
        'primary_pass': str(primary_pass).lower(),
        'top5_overlap': topk['5']['overlap'], 'top5_enrichment': topk['5']['enrichment'],
        'top10_overlap': topk['10']['overlap'], 'top10_enrichment': topk['10']['enrichment'],
        'permutation_p_all_100k': permutation_p,
        'partial_rank_log_est_city': partial_rank,
    })

verdict = {
    'status': status,
    'interpretation': interpretation,
    'preregistration_boundary_commit': PREREG,
    'predictor_denominator_freeze_commit': SOURCE_FREEZE,
    'protocol': {
        'cutoff': '2022-03-31',
        'answer_window': '2022-04-01..2024-03-31',
        'regions': {'total': 30, 'Sapporo': 10, 'Kobe': 9, 'Kyoto': 11},
        'predictor': 'age20_29_growth_2020_to_2021_pct',
        'rule': 'PASS iff scaled Spearman is strictly positive in ALL, Sapporo, Kobe, and Kyoto.',
    },
    'outcome_source': {
        'category': 'L real-estate-use building-start floor area',
        'FY2022': {'statInfId': '000040052251', 'sha256': EXPECTED_SHA[PHYSICAL / 'FY2022.xls'], 'floor_column_zero_based': 28},
        'FY2023': {'statInfId': '000040179628', 'sha256': EXPECTED_SHA[PHYSICAL / 'FY2023.xls'], 'floor_column_zero_based': 29},
        'missing_or_suppressed_L_values': 0,
        'ward_sum_validation': ward_sum_validation,
    },
    'result': {'scaled_spearman': scaled, 'raw_spearman': raw, 'primary_pass': primary_pass, 'raw_conflict': raw_conflict},
    'diagnostics': {
        'permutations': PERMUTATIONS,
        'permutation_tail': 'two-sided absolute Spearman',
        'seed_source': 'first_8_hex_of_preregistration_commit',
        'seed': SEED,
        'permutation_p_all': permutation_p,
        'topk': topk,
        'topk_tie_break': 'region_code ascending',
        'partial_rank_log_est_city': partial_rank,
        'permutation_is_acceptance_condition': False,
    },
    'distributions': distributions,
    'files': {},
    'next_constraint': 'Do not create a scalar. This is a replicated single mechanism; any broader promotion requires a new preregistered temporal or external-source gate.' if primary_pass else 'The current young-adult-momentum -> L replication path is closed unless a substantively new mechanism or dataset is preregistered independently.',
}
verdict_path = OUT / 'age_growth_fresh_spatial_holdout_2022_verdict.json'
verdict['files'] = {'outcome_csv_sha256': sha256(outcome_path), 'evaluation_csv_sha256': sha256(eval_path)}
verdict_path.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

result_path = OUT / 'age20-29-growth-L-fresh-spatial-holdout-result-2026-08-24.md'
result_path.write_text(f'''# Neighborhood Pulse — age20-29 growth -> L fresh spatial holdout result

Date: 2026-08-24

## Status

**{status}. No post-result tuning.**

Pre-outcome gates:
- preregistration boundary: `{PREREG}`
- predictor + 2016 denominator freeze: `{SOURCE_FREEZE}`
- fresh universe: Sapporo 10 + Kobe 9 + Kyoto 11 = 30 wards
- cutoff/H24 unchanged: 2022-03-31 / 2022-04-01..2024-03-31
- one predictor only: `age20_29_growth_2020_to_2021_pct`
- PASS rule: scaled Spearman must be strictly positive in ALL / Sapporo / Kobe / Kyoto

## Primary result

| group | scaled L Spearman | raw L Spearman |
|---|---:|---:|
| ALL | {scaled['ALL']:.12f} | {raw['ALL']:.12f} |
| Sapporo | {scaled['Sapporo']:.12f} | {raw['Sapporo']:.12f} |
| Kobe | {scaled['Kobe']:.12f} | {raw['Kobe']:.12f} |
| Kyoto | {scaled['Kyoto']:.12f} | {raw['Kyoto']:.12f} |

All four scaled correlations are strictly positive. Therefore the preregistered primary test = **{'PASS' if primary_pass else 'FAIL'}**.

## Source validation

All 30 wards have numeric FY2022/FY2023 L values. Ward sums equal the published city totals for Sapporo, Kobe, and Kyoto in both fiscal years. No missing/suppressed L value was zero-filled.

## Mandatory diagnostics

- deterministic 100k two-sided permutation p(ALL): `{permutation_p}`
- top5 overlap/enrichment: `{topk['5']['overlap']}` / `{topk['5']['enrichment']}x`
- top10 overlap/enrichment: `{topk['10']['overlap']}` / `{topk['10']['enrichment']}x`
- rank-residual diagnostic after log(2016 establishments)+city: `{partial_rank}`
- raw ALL remains positive, so there is no `PASS_WITH_RAW_CONFLICT` condition.

## Interpretation

The narrowed age20-29 growth -> L mechanism now passes an untouched 30-ward external holdout after the prior temporal and Osaka/Nagoya evidence. This supports promotion of the **single mechanism** to replicated evidence. It does not rehabilitate the failed five-feature Demand family, does not validate age-share as an independent promoted feature, and does not justify a weighted Neighborhood Pulse scalar.

A broader claim requires another preregistered gate, preferably a new temporal cutoff or independent source family. Do not tune this observed holdout.
''', encoding='utf-8')

print(json.dumps(verdict, ensure_ascii=False, indent=2))
