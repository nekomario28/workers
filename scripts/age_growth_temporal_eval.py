import csv
import hashlib
import io
import json
import math
import random
import re
import unicodedata
from pathlib import Path

import numpy as np
import xlrd

OUT = Path('/tmp/out')
SRC = Path('/tmp/source')
OUT.mkdir(parents=True, exist_ok=True)

PREREG = 'c935789e105a0476c05ff24ff599a42660a35491'
PRED_FREEZE = 'd8768eb08f7e71484669c27a230bf3cde757f707'
SOURCE_FREEZE = '1f51e882bc6da7ea07087a6a6c4af031906122d2'
SEED = int(PREREG[:8], 16)
PERMUTATIONS = 100000

PRED_CSV = '''region_code,region_name,metro,age20_29_growth_2022_to_2023_pct
01101,札幌市中央区,Sapporo,1.9663313774797464
01102,札幌市北区,Sapporo,1.5055917209147118
01103,札幌市東区,Sapporo,-0.685925818392974
01104,札幌市白石区,Sapporo,0.23300324540234119
01105,札幌市豊平区,Sapporo,1.21440848964951
01106,札幌市南区,Sapporo,-1.4946418499718006
01107,札幌市西区,Sapporo,0.8292443572129438
01108,札幌市厚別区,Sapporo,-1.3622173871913779
01109,札幌市手稲区,Sapporo,-0.72075401958972
01110,札幌市清田区,Sapporo,-0.8271713247274048
28101,神戸市東灘区,Kobe,0.632824322465253
28102,神戸市灘区,Kobe,3.0846688412990986
28105,神戸市兵庫区,Kobe,8.963585434173659
28106,神戸市長田区,Kobe,3.7486435829140685
28107,神戸市須磨区,Kobe,-0.20595807282088874
28108,神戸市垂水区,Kobe,-2.1262495167614692
28109,神戸市北区,Kobe,-0.8989245010433966
28110,神戸市中央区,Kobe,3.291649441918154
28111,神戸市西区,Kobe,-1.3165477193137987
26101,京都市北区,Kyoto,2.055516514406186
26102,京都市上京区,Kyoto,9.756851432103852
26103,京都市左京区,Kyoto,4.86175240371558
26104,京都市中京区,Kyoto,5.178629957391023
26105,京都市東山区,Kyoto,6.754931099702777
26106,京都市下京区,Kyoto,7.017716535433061
26107,京都市南区,Kyoto,3.7677234347618382
26108,京都市右京区,Kyoto,1.7066031651535418
26109,京都市伏見区,Kyoto,1.4060853530031503
26110,京都市山科区,Kyoto,0.2346213065474112
26111,京都市西京区,Kyoto,-1.6382742640819736
'''
PRED_SHA = '08424075067deb113bee91918b79eadadbbdc9dfeefe8eb17d462b3b636de067'

DENOM_CSV = '''region_code,region_name,metro,private_establishments_2016,source_row
01101,札幌市中央区,Sapporo,22135,15
01102,札幌市北区,Sapporo,8835,16
01103,札幌市東区,Sapporo,8485,17
01104,札幌市白石区,Sapporo,7786,18
01105,札幌市豊平区,Sapporo,5993,19
01106,札幌市南区,Sapporo,3464,20
01107,札幌市西区,Sapporo,6652,21
01108,札幌市厚別区,Sapporo,2847,22
01109,札幌市手稲区,Sapporo,3274,23
01110,札幌市清田区,Sapporo,2980,24
28101,神戸市東灘区,Kobe,7291,1531
28102,神戸市灘区,Kobe,5357,1532
28105,神戸市兵庫区,Kobe,6833,1533
28106,神戸市長田区,Kobe,5544,1534
28107,神戸市須磨区,Kobe,4129,1535
28108,神戸市垂水区,Kobe,5026,1536
28109,神戸市北区,Kobe,5105,1537
28110,神戸市中央区,Kobe,21258,1538
28111,神戸市西区,Kobe,6339,1539
26101,京都市北区,Kyoto,5119,1407
26102,京都市上京区,Kyoto,5048,1408
26103,京都市左京区,Kyoto,6719,1409
26104,京都市中京区,Kyoto,9871,1410
26105,京都市東山区,Kyoto,4192,1411
26106,京都市下京区,Kyoto,8502,1412
26107,京都市南区,Kyoto,5743,1413
26108,京都市右京区,Kyoto,7648,1414
26109,京都市伏見区,Kyoto,9181,1415
26110,京都市山科区,Kyoto,4446,1416
26111,京都市西京区,Kyoto,4168,1417
'''
DENOM_SHA = '0a6bf537b805fc31518c6af297d2b11ad523169ee610c39d943d7c895bdcf1e0'

if hashlib.sha256(PRED_CSV.encode()).hexdigest() != PRED_SHA:
    raise SystemExit('embedded canonical predictor CSV SHA mismatch')
if hashlib.sha256(DENOM_CSV.encode()).hexdigest() != DENOM_SHA:
    raise SystemExit('embedded canonical denominator CSV SHA mismatch')

pred_rows = list(csv.DictReader(io.StringIO(PRED_CSV)))
denom_rows = list(csv.DictReader(io.StringIO(DENOM_CSV)))
if len(pred_rows) != 30 or len(denom_rows) != 30:
    raise SystemExit('expected 30 frozen rows')
if [r['region_code'] for r in pred_rows] != [r['region_code'] for r in denom_rows]:
    raise SystemExit('predictor/denominator order mismatch')

codes = [r['region_code'] for r in pred_rows]
names = {r['region_code']: r['region_name'] for r in pred_rows}
metros = {r['region_code']: r['metro'] for r in pred_rows}
predictor = {r['region_code']: float(r['age20_29_growth_2022_to_2023_pct']) for r in pred_rows}
denominator = {r['region_code']: int(r['private_establishments_2016']) for r in denom_rows}
CITY = {'Sapporo': '01100', 'Kobe': '28100', 'Kyoto': '26100'}
TARGETS = set(codes) | set(CITY.values())

SOURCES = [
    {
        'key': 'FY2024_apr_dec',
        'path': SRC / 'FY2024_7-2_apr-dec.xls',
        'statInfId': '000040273624',
        'coverage': '2024-04-01..2024-12-31',
        'sha256': 'dc7a7197aa40a600752b20fc218268523cde9148f85caaae69b31b0398f3996a',
    },
    {
        'key': 'FY2024_jan_mar',
        'path': SRC / 'FY2024_7-2-2_jan-mar.xls',
        'statInfId': '000040273625',
        'coverage': '2025-01-01..2025-03-31',
        'sha256': 'a5217bdf9873ca4188a98a6e13bb34c62bffb02d7e0c4d0691053a231bec08d8',
    },
    {
        'key': 'FY2025_full',
        'path': SRC / 'FY2025_7-2-2_full-year.xls',
        'statInfId': '000040451288',
        'coverage': '2025-04-01..2026-03-31',
        'sha256': '6dd12e3315b77ae67688839b789e046d52e29826b2b5c8312fa339581686a1a9',
    },
]

for s in SOURCES:
    got = hashlib.sha256(s['path'].read_bytes()).hexdigest()
    if got != s['sha256']:
        raise SystemExit(f"source SHA mismatch {s['path'].name}: {got}")


def norm(v):
    return ''.join(unicodedata.normalize('NFKC', str(v or '')).split())


def code_from_cell(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        fv = float(v)
        if math.isfinite(fv) and fv.is_integer() and 0 < fv < 100000:
            return f'{int(fv):05d}'
    s = norm(v)
    m = re.search(r'(?<!\d)(\d{5})(?:\d)?', s)
    if m:
        return m.group(1)
    if s.isdigit() and 1 <= len(s) <= 5:
        return s.zfill(5)
    return None


def locate_l_floor_column(sh):
    top = min(50, sh.nrows)
    candidates = []
    evidence = []
    for r in range(top):
        for c in range(sh.ncols):
            txt = norm(sh.cell_value(r, c))
            if '不動産業' not in txt:
                continue
            span = (c, c + 1)
            for rlo, rhi, clo, chi in sh.merged_cells:
                if rlo <= r < rhi and clo <= c < chi:
                    span = (clo, chi)
                    break
            floor_cols = []
            for cc in range(span[0], span[1]):
                for rr in range(r, top):
                    if '床面積' in norm(sh.cell_value(rr, cc)):
                        floor_cols.append(cc)
                        break
            floor_cols = sorted(set(floor_cols))
            evidence.append({'header_row': r, 'header_col': c, 'header': txt, 'span': list(span), 'floor_cols': floor_cols})
            if len(floor_cols) == 1:
                candidates.append(floor_cols[0])
            elif span[1] - span[0] == 2:
                # Table 7-2 family convention: subcolumns are 棟数 then 床面積.
                left_has_count = any('棟数' in norm(sh.cell_value(rr, span[0])) for rr in range(r, top))
                right_has_floor = any('床面積' in norm(sh.cell_value(rr, span[1] - 1)) for rr in range(r, top))
                if left_has_count and right_has_floor:
                    candidates.append(span[1] - 1)
    candidates = sorted(set(candidates))
    if len(candidates) != 1:
        raise SystemExit('L floor column is not uniquely identified: ' + json.dumps({'candidates': candidates, 'evidence': evidence}, ensure_ascii=False))
    return candidates[0], evidence


def parse_source(spec):
    wb = xlrd.open_workbook(spec['path'], on_demand=True, formatting_info=True)
    sh = wb.sheet_by_index(0)
    l_col, evidence = locate_l_floor_column(sh)
    values = {}
    row_locations = {}
    for i in range(sh.nrows):
        code = None
        for c in range(min(8, sh.ncols)):
            x = code_from_cell(sh.cell_value(i, c))
            if x in TARGETS:
                code = x
                break
        if code is None:
            continue
        if code in values:
            raise SystemExit(f"duplicate target row {spec['path'].name} {code}")
        cell = sh.cell_value(i, l_col)
        if isinstance(cell, str):
            if cell.strip() == '':
                raise SystemExit(f"missing L value {spec['path'].name} {code}")
            raise SystemExit(f"nonnumeric/suppressed L value {spec['path'].name} {code}: {cell!r}")
        try:
            val = float(cell)
        except Exception:
            raise SystemExit(f"invalid L value {spec['path'].name} {code}: {cell!r}")
        if not math.isfinite(val) or val < 0:
            raise SystemExit(f"invalid numeric L value {spec['path'].name} {code}: {val}")
        values[code] = val
        row_locations[code] = i
    wb.release_resources()
    missing = TARGETS - set(values)
    if missing:
        raise SystemExit(f"missing target rows {spec['path'].name}: {sorted(missing)}")
    city_validation = {}
    for metro, city_code in CITY.items():
        ward_sum = sum(values[c] for c in codes if metros[c] == metro)
        city_total = values[city_code]
        if abs(ward_sum - city_total) > 1e-9:
            raise SystemExit(f"ward/city total mismatch {spec['path'].name} {metro}: {ward_sum} != {city_total}")
        city_validation[metro] = {'ward_sum': ward_sum, 'city_total': city_total, 'matches': True}
    return values, {
        'file': spec['path'].name,
        'statInfId': spec['statInfId'],
        'coverage': spec['coverage'],
        'sha256': spec['sha256'],
        'sheet': sh.name,
        'nrows': sh.nrows,
        'ncols': sh.ncols,
        'L_floor_column_zero_based': l_col,
        'header_evidence': evidence,
        'row_locations': row_locations,
        'ward_sum_validation': city_validation,
    }

parsed = {}
parser_receipts = []
for spec in SOURCES:
    vals, rec = parse_source(spec)
    parsed[spec['key']] = vals
    parser_receipts.append(rec)

rows = []
for code in codes:
    part1 = parsed['FY2024_apr_dec'][code]
    part2 = parsed['FY2024_jan_mar'][code]
    part3 = parsed['FY2025_full'][code]
    h24 = part1 + part2 + part3
    est = denominator[code]
    if est <= 0:
        raise SystemExit(f'nonpositive denominator {code}')
    rows.append({
        'region_code': code,
        'region_name': names[code],
        'metro': metros[code],
        'age20_29_growth_2022_to_2023_pct': predictor[code],
        'private_establishments_2016': est,
        'floor_area_L_2024_apr_dec': part1,
        'floor_area_L_2025_jan_mar': part2,
        'floor_area_L_FY2024': part1 + part2,
        'floor_area_L_FY2025': part3,
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
    x = [r['age20_29_growth_2022_to_2023_pct'] for r in subset]
    scaled[group] = spearman(x, [r['execution_L_per_est_2016'] for r in subset])
    raw[group] = spearman(x, [r['floor_area_L_h24'] for r in subset])

primary_pass = all(math.isfinite(scaled[g]) and scaled[g] > 0 for g in groups)
status = 'PASS_TEMPORAL_REVALIDATION' if primary_pass else 'FAIL_TEMPORAL_REVALIDATION'
raw_conflict = primary_pass and raw['ALL'] <= 0
interpretation = 'PASS_WITH_RAW_CONFLICT' if raw_conflict else status

xr = ranks([r['age20_29_growth_2022_to_2023_pct'] for r in rows])
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
    overlap = len(top_codes('age20_29_growth_2022_to_2023_pct', k) & top_codes('execution_L_per_est_2016', k))
    topk[str(k)] = {'overlap': overlap, 'enrichment': overlap * len(rows) / (k*k)}

rx = np.asarray(ranks([r['age20_29_growth_2022_to_2023_pct'] for r in rows]), dtype=float)
ry = np.asarray(ranks([r['execution_L_per_est_2016'] for r in rows]), dtype=float)
log_est = np.log(np.asarray([r['private_establishments_2016'] for r in rows], dtype=float))
kyoto = np.asarray([1.0 if r['metro'] == 'Kyoto' else 0.0 for r in rows])
sapporo = np.asarray([1.0 if r['metro'] == 'Sapporo' else 0.0 for r in rows])
X = np.column_stack([np.ones(len(rows)), log_est, kyoto, sapporo])
bx = np.linalg.lstsq(X, rx, rcond=None)[0]
by = np.linalg.lstsq(X, ry, rcond=None)[0]
partial_rank = float(np.corrcoef(rx - X @ bx, ry - X @ by)[0, 1])


def dist(values):
    vals = sorted(float(v) for v in values)
    n = len(vals)
    med = vals[n//2] if n % 2 else (vals[n//2 - 1] + vals[n//2]) / 2.0
    return {
        'n': n,
        'min': min(vals),
        'median': med,
        'mean': sum(vals) / n,
        'max': max(vals),
        'zero_count': sum(v == 0 for v in vals),
        'unique_count': len(set(vals)),
        'tie_observation_count': n - len(set(vals)),
    }

distributions = {'L': {}, 'private_establishments_2016': {}}
for group in groups:
    subset = group_rows(group)
    distributions['L'][group] = {
        'raw_L': dist([r['floor_area_L_h24'] for r in subset]),
        'scaled_L': dist([r['execution_L_per_est_2016'] for r in subset]),
    }
    distributions['private_establishments_2016'][group] = dist([r['private_establishments_2016'] for r in subset])

outcome_path = OUT / 'age_growth_temporal_revalidation_2024_outcome_30regions.csv'
with outcome_path.open('w', encoding='utf-8', newline='') as f:
    fields = ['region_code','region_name','metro','floor_area_L_2024_apr_dec','floor_area_L_2025_jan_mar','floor_area_L_FY2024','floor_area_L_FY2025','floor_area_L_h24','execution_L_per_est_2016']
    w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
    w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in fields})

eval_path = OUT / 'age_growth_temporal_revalidation_2024_evaluation.csv'
with eval_path.open('w', encoding='utf-8', newline='') as f:
    fields = ['predictor','scaled_ALL','scaled_Sapporo','scaled_Kobe','scaled_Kyoto','raw_ALL','raw_Sapporo','raw_Kobe','raw_Kyoto','primary_pass','top5_overlap','top5_enrichment','top10_overlap','top10_enrichment','permutation_p_all_100k','partial_rank_log_est_city']
    w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
    w.writeheader()
    w.writerow({
        'predictor': 'age20_29_growth_2022_to_2023_pct',
        'scaled_ALL': scaled['ALL'], 'scaled_Sapporo': scaled['Sapporo'], 'scaled_Kobe': scaled['Kobe'], 'scaled_Kyoto': scaled['Kyoto'],
        'raw_ALL': raw['ALL'], 'raw_Sapporo': raw['Sapporo'], 'raw_Kobe': raw['Kobe'], 'raw_Kyoto': raw['Kyoto'],
        'primary_pass': str(primary_pass).lower(),
        'top5_overlap': topk['5']['overlap'], 'top5_enrichment': topk['5']['enrichment'],
        'top10_overlap': topk['10']['overlap'], 'top10_enrichment': topk['10']['enrichment'],
        'permutation_p_all_100k': permutation_p,
        'partial_rank_log_est_city': partial_rank,
    })

parser_path = OUT / 'age_growth_temporal_revalidation_2024_parser_receipt.json'
parser_receipt = {
    'status': 'PARSED_ONCE_FROM_PRE_FROZEN_SOURCE_BYTES',
    'source_freeze_commit': SOURCE_FREEZE,
    'sources': parser_receipts,
    'missing_or_suppressed_values_zero_filled': False,
}
parser_path.write_text(json.dumps(parser_receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

verdict = {
    'status': status,
    'interpretation': interpretation,
    'preregistration_commit': PREREG,
    'predictor_freeze_commit': PRED_FREEZE,
    'outcome_source_freeze_commit': SOURCE_FREEZE,
    'protocol': {
        'predictor_years': '2022-01-01 and 2023-01-01 snapshots',
        'cutoff': '2024-03-31',
        'answer_window': '2024-04-01..2026-03-31',
        'regions': {'total': 30, 'Sapporo': 10, 'Kobe': 9, 'Kyoto': 11},
        'predictor': 'age20_29_growth_2022_to_2023_pct',
        'outcome': 'FY2024 + FY2025 L real-estate-use building-start floor area / 2016 private establishments',
        'rule': 'PASS iff scaled Spearman is strictly positive in ALL, Sapporo, Kobe, and Kyoto.',
    },
    'result': {
        'scaled_spearman': scaled,
        'raw_spearman': raw,
        'primary_pass': primary_pass,
        'raw_conflict': raw_conflict,
    },
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
    'source_parse_receipt_sha256': sha(parser_path),
    'files': {
        'outcome_csv_sha256': sha(outcome_path),
        'evaluation_csv_sha256': sha(eval_path),
    },
    'post_result_tuning': False,
    'next_constraint': 'If PASS, the single age20-29 growth -> L mechanism has both fresh spatial and later temporal replication; broader mechanism families or scalar scores remain unsupported.' if primary_pass else 'If FAIL, cap the claim at the prior-window fresh spatial replication and do not retune this observed temporal window.',
}
verdict_path = OUT / 'age_growth_temporal_revalidation_2024_verdict.json'
verdict_path.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

result_path = OUT / 'age20-29-growth-L-temporal-revalidation-result-2026-08-24.md'
result_path.write_text(f'''# Neighborhood Pulse — age20-29 growth -> L temporal revalidation result

Date: 2026-08-24

## Status

**{status}. No post-result tuning.**

Pre-outcome gates:
- preregistration: `{PREREG}`
- predictor freeze: `{PRED_FREEZE}`
- outcome source-byte freeze before parse: `{SOURCE_FREEZE}`
- fixed universe: Sapporo 10 + Kobe 9 + Kyoto 11 = 30 wards
- cutoff/H24: 2024-03-31 / 2024-04-01..2026-03-31
- one predictor only: `age20_29_growth_2022_to_2023_pct`
- unchanged 2016 private-establishment denominator
- PASS rule: scaled Spearman strictly positive in ALL / Sapporo / Kobe / Kyoto

## Primary result

| group | scaled L Spearman | raw L Spearman |
|---|---:|---:|
| ALL | {scaled['ALL']:.12f} | {raw['ALL']:.12f} |
| Sapporo | {scaled['Sapporo']:.12f} | {raw['Sapporo']:.12f} |
| Kobe | {scaled['Kobe']:.12f} | {raw['Kobe']:.12f} |
| Kyoto | {scaled['Kyoto']:.12f} | {raw['Kyoto']:.12f} |

Primary rule = **{'PASS' if primary_pass else 'FAIL'}**.

## Source validation

The FY2024/FY2025 source bytes were frozen before any outcome parse. The evaluator identified the `L 不動産業用建築物` floor-area column from workbook header/merged-cell structure instead of reusing an old column number. For every source segment, all 30 wards were numeric and each city's ward sum matched its published city total. Missing/suppressed cells were not zero-filled.

## Mandatory diagnostics

- deterministic 100k two-sided permutation p(ALL): `{permutation_p}`
- top5 overlap/enrichment: `{topk['5']['overlap']}` / `{topk['5']['enrichment']}x`
- top10 overlap/enrichment: `{topk['10']['overlap']}` / `{topk['10']['enrichment']}x`
- rank-residual diagnostic after log(2016 establishments)+city: `{partial_rank}`
- raw-conflict flag: `{str(raw_conflict).lower()}`

## Interpretation

{'The narrowed age20-29 growth -> L mechanism survives a later two-year temporal window on the same untouched 30-ward universe. Together with the earlier fresh spatial PASS, this supports replicated evidence for the single mechanism only.' if primary_pass else 'The narrowed mechanism does not survive the later temporal window. The prior fresh spatial PASS remains valid evidence for that earlier window, but the mechanism is not temporally durable under this preregistered revalidation.'}

The failed five-feature Demand family remains failed. Do not create a weighted Neighborhood Pulse scalar from this result.
''', encoding='utf-8')

print(json.dumps(verdict, ensure_ascii=False, indent=2))
