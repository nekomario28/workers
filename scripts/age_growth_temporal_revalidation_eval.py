import csv
import hashlib
import json
import math
import random
import re
from pathlib import Path

import numpy as np
import xlrd

OUT = Path('/tmp/out')
SRC = Path('/tmp/outcome-source')
OUT.mkdir(parents=True, exist_ok=True)

PREREG = 'c935789e105a0476c05ff24ff599a42660a35491'
PRED_FREEZE = 'd8768eb08f7e71484669c27a230bf3cde757f707'
SOURCE_FREEZE = '1f51e882bc6da7ea07087a6a6c4af031906122d2'
SEED = int(PREREG[:8], 16)
PERMUTATIONS = 100000

regions = [
('01101','札幌市中央区','Sapporo',1.9663313774797464,22135,15),
('01102','札幌市北区','Sapporo',1.5055917209147118,8835,16),
('01103','札幌市東区','Sapporo',-0.685925818392974,8485,17),
('01104','札幌市白石区','Sapporo',0.23300324540234119,7786,18),
('01105','札幌市豊平区','Sapporo',1.21440848964951,5993,19),
('01106','札幌市南区','Sapporo',-1.4946418499718006,3464,20),
('01107','札幌市西区','Sapporo',0.8292443572129438,6652,21),
('01108','札幌市厚別区','Sapporo',-1.3622173871913779,2847,22),
('01109','札幌市手稲区','Sapporo',-0.72075401958972,3274,23),
('01110','札幌市清田区','Sapporo',-0.8271713247274048,2980,24),
('28101','神戸市東灘区','Kobe',0.632824322465253,7291,1531),
('28102','神戸市灘区','Kobe',3.0846688412990986,5357,1532),
('28105','神戸市兵庫区','Kobe',8.963585434173659,6833,1533),
('28106','神戸市長田区','Kobe',3.7486435829140685,5544,1534),
('28107','神戸市須磨区','Kobe',-0.20595807282088874,4129,1535),
('28108','神戸市垂水区','Kobe',-2.1262495167614692,5026,1536),
('28109','神戸市北区','Kobe',-0.8989245010433966,5105,1537),
('28110','神戸市中央区','Kobe',3.291649441918154,21258,1538),
('28111','神戸市西区','Kobe',-1.3165477193137987,6339,1539),
('26101','京都市北区','Kyoto',2.055516514406186,5119,1407),
('26102','京都市上京区','Kyoto',9.756851432103852,5048,1408),
('26103','京都市左京区','Kyoto',4.86175240371558,6719,1409),
('26104','京都市中京区','Kyoto',5.178629957391023,9871,1410),
('26105','京都市東山区','Kyoto',6.754931099702777,4192,1411),
('26106','京都市下京区','Kyoto',7.017716535433061,8502,1412),
('26107','京都市南区','Kyoto',3.7677234347618382,5743,1413),
('26108','京都市右京区','Kyoto',1.7066031651535418,7648,1414),
('26109','京都市伏見区','Kyoto',1.4060853530031503,9181,1415),
('26110','京都市山科区','Kyoto',0.2346213065474112,4446,1416),
('26111','京都市西京区','Kyoto',-1.6382742640819736,4168,1417),
]
if len(regions) != 30 or len({r[0] for r in regions}) != 30:
    raise SystemExit('invalid region universe')

# Reconstruct the exact canonical predictor and denominator freezes so transport
# cannot silently drift from the private canonical authority.
pred_path = Path('/tmp/predictor.csv')
with pred_path.open('w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['region_code','region_name','metro','age20_29_growth_2022_to_2023_pct'])
    for code,name,metro,growth,est,row in regions:
        w.writerow([code,name,metro,growth])
if hashlib.sha256(pred_path.read_bytes()).hexdigest() != '08424075067deb113bee91918b79eadadbbdc9dfeefe8eb17d462b3b636de067':
    raise SystemExit('canonical predictor reconstruction hash mismatch')

denom_path = Path('/tmp/denominator.csv')
with denom_path.open('w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['region_code','region_name','metro','private_establishments_2016','source_row'])
    for code,name,metro,growth,est,row in regions:
        w.writerow([code,name,metro,est,row])
if hashlib.sha256(denom_path.read_bytes()).hexdigest() != '0a6bf537b805fc31518c6af297d2b11ad523169ee610c39d943d7c895bdcf1e0':
    raise SystemExit('canonical denominator reconstruction hash mismatch')

expected_sources = {
    'FY2024_7-2_apr-dec.xls': 'dc7a7197aa40a600752b20fc218268523cde9148f85caaae69b31b0398f3996a',
    'FY2024_7-2-2_jan-mar.xls': 'a5217bdf9873ca4188a98a6e13bb34c62bffb02d7e0c4d0691053a231bec08d8',
    'FY2025_7-2-2_full-year.xls': '6dd12e3315b77ae67688839b789e046d52e29826b2b5c8312fa339581686a1a9',
}
for name, sha in expected_sources.items():
    p = SRC / name
    if hashlib.sha256(p.read_bytes()).hexdigest() != sha:
        raise SystemExit(f'outcome source SHA mismatch {name}')

codes = [r[0] for r in regions]
metro_by_code = {r[0]: r[2] for r in regions}
name_by_code = {r[0]: r[1] for r in regions}
predictor = {r[0]: r[3] for r in regions}
denominator = {r[0]: r[4] for r in regions}
city_codes = {'Sapporo':'01100','Kobe':'28100','Kyoto':'26100'}
targets = set(codes) | set(city_codes.values())


def as_text(v):
    if v is None:
        return ''
    return str(v).strip()


def find_l_floor_column(sh):
    header_rows = min(24, sh.nrows)
    merged_labels = [[] for _ in range(sh.ncols)]
    for rlo, rhi, clo, chi in sh.merged_cells:
        if rlo >= header_rows or clo >= sh.ncols:
            continue
        label = as_text(sh.cell_value(rlo, clo))
        if not label:
            continue
        for c in range(clo, min(chi, sh.ncols)):
            merged_labels[c].append(label)
    candidates = []
    diagnostics = []
    for c in range(sh.ncols):
        toks = list(merged_labels[c])
        for r in range(header_rows):
            v = sh.cell_value(r, c)
            if isinstance(v, str) and v.strip():
                toks.append(v.strip())
        text = '|'.join(toks)
        if '不動産業' in text:
            diagnostics.append((c, text))
            if '床面積' in text:
                candidates.append(c)
    if len(candidates) != 1:
        raise SystemExit('L floor header column not unique: candidates=' + repr(candidates) + ' diag=' + repr(diagnostics))
    return candidates[0], diagnostics


def extract_period(path):
    wb = xlrd.open_workbook(str(path), formatting_info=False, on_demand=True)
    sh = wb.sheet_by_index(0)
    lcol, header_diag = find_l_floor_column(sh)
    values = {}
    row_index = {}
    for i in range(sh.nrows):
        code = None
        for j in range(min(5, sh.ncols)):
            s = as_text(sh.cell_value(i, j))
            m = re.match(r'^(\d{5})', s)
            if m and m.group(1) in targets:
                code = m.group(1)
                break
        if not code:
            continue
        cell = sh.cell_value(i, lcol)
        if isinstance(cell, bool):
            raise SystemExit(f'boolean L cell {path.name} {code}')
        if isinstance(cell, (int, float)):
            val = float(cell)
        else:
            s = as_text(cell)
            try:
                val = float(s.replace(',', ''))
            except Exception:
                raise SystemExit(f'missing/suppressed/non-numeric L cell {path.name} {code}: {cell!r}')
        if not math.isfinite(val) or val < 0:
            raise SystemExit(f'invalid L value {path.name} {code}: {val}')
        values[code] = val
        row_index[code] = i
    wb.release_resources()
    missing = targets - set(values)
    if missing:
        raise SystemExit(f'missing target rows {path.name}: {sorted(missing)}')
    validation = {}
    for metro, city_code in city_codes.items():
        ward_sum = sum(values[c] for c in codes if metro_by_code[c] == metro)
        city_total = values[city_code]
        if abs(ward_sum - city_total) > 1e-9:
            raise SystemExit(f'ward sum mismatch {path.name} {metro}: {ward_sum} != {city_total}')
        validation[metro] = {'ward_sum': ward_sum, 'city_total': city_total, 'matches': True}
    return values, {'l_floor_column_zero_based': lcol, 'ward_sum_validation': validation, 'row_index': row_index}

period_specs = [
    ('FY2024_apr_dec', SRC/'FY2024_7-2_apr-dec.xls', '000040273624', '2024-04-01..2024-12-31'),
    ('FY2024_jan_mar', SRC/'FY2024_7-2-2_jan-mar.xls', '000040273625', '2025-01-01..2025-03-31'),
    ('FY2025_full', SRC/'FY2025_7-2-2_full-year.xls', '000040451288', '2025-04-01..2026-03-31'),
]
period_values = {}
period_meta = {}
for key, path, sid, coverage in period_specs:
    values, meta = extract_period(path)
    period_values[key] = values
    period_meta[key] = {
        'statInfId': sid,
        'coverage': coverage,
        'sha256': expected_sources[path.name],
        **{k:v for k,v in meta.items() if k != 'row_index'},
    }

rows = []
for code,name,metro,growth,est,source_row in regions:
    fy2024 = period_values['FY2024_apr_dec'][code] + period_values['FY2024_jan_mar'][code]
    fy2025 = period_values['FY2025_full'][code]
    h24 = fy2024 + fy2025
    rows.append({
        'region_code': code,
        'region_name': name,
        'metro': metro,
        'age20_29_growth_2022_to_2023_pct': growth,
        'private_establishments_2016': est,
        'floor_area_L_FY2024_apr_dec': period_values['FY2024_apr_dec'][code],
        'floor_area_L_FY2024_jan_mar': period_values['FY2024_jan_mar'][code],
        'floor_area_L_FY2024': fy2024,
        'floor_area_L_FY2025': fy2025,
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


def pearson(a,b):
    ma=sum(a)/len(a); mb=sum(b)/len(b)
    da=[v-ma for v in a]; db=[v-mb for v in b]
    den=math.sqrt(sum(v*v for v in da)*sum(v*v for v in db))
    if den == 0: return float('nan')
    return sum(x*y for x,y in zip(da,db))/den


def spearman(a,b):
    return pearson(ranks(a),ranks(b))


def group_rows(group):
    return rows if group == 'ALL' else [r for r in rows if r['metro'] == group]

groups=['ALL','Sapporo','Kobe','Kyoto']
scaled={}; raw={}
for g in groups:
    sub=group_rows(g)
    x=[r['age20_29_growth_2022_to_2023_pct'] for r in sub]
    scaled[g]=spearman(x,[r['execution_L_per_est_2016'] for r in sub])
    raw[g]=spearman(x,[r['floor_area_L_h24'] for r in sub])
primary_pass=all(scaled[g] > 0 for g in groups)
status='PASS_TEMPORAL_REVALIDATION' if primary_pass else 'FAIL_TEMPORAL_REVALIDATION'
raw_conflict=primary_pass and raw['ALL'] <= 0
interpretation='PASS_WITH_RAW_CONFLICT' if raw_conflict else status

xr=ranks([r['age20_29_growth_2022_to_2023_pct'] for r in rows])
yr=ranks([r['execution_L_per_est_2016'] for r in rows])
obs=pearson(xr,yr)
rng=random.Random(SEED)
exceed=0
for _ in range(PERMUTATIONS):
    yp=list(yr); rng.shuffle(yp)
    if abs(pearson(xr,yp)) >= abs(obs) - 1e-15:
        exceed += 1
permutation_p=(exceed+1)/(PERMUTATIONS+1)


def top_codes(field,k):
    return {r['region_code'] for r in sorted(rows,key=lambda r:(-r[field],r['region_code']))[:k]}
topk={}
for k in (5,10):
    overlap=len(top_codes('age20_29_growth_2022_to_2023_pct',k)&top_codes('execution_L_per_est_2016',k))
    topk[str(k)]={'overlap':overlap,'enrichment':overlap*len(rows)/(k*k)}

rx=np.asarray(ranks([r['age20_29_growth_2022_to_2023_pct'] for r in rows]),dtype=float)
ry=np.asarray(ranks([r['execution_L_per_est_2016'] for r in rows]),dtype=float)
log_est=np.log(np.asarray([r['private_establishments_2016'] for r in rows],dtype=float))
kyoto=np.asarray([1.0 if r['metro']=='Kyoto' else 0.0 for r in rows])
sapporo=np.asarray([1.0 if r['metro']=='Sapporo' else 0.0 for r in rows])
X=np.column_stack([np.ones(len(rows)),log_est,kyoto,sapporo])
res_x=rx-X@np.linalg.lstsq(X,rx,rcond=None)[0]
res_y=ry-X@np.linalg.lstsq(X,ry,rcond=None)[0]
partial_rank=float(np.corrcoef(res_x,res_y)[0,1])


def dist(values):
    vals=sorted(float(v) for v in values); n=len(vals); u=len(set(vals))
    med=vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/2
    return {'n':n,'min':min(vals),'median':med,'mean':sum(vals)/n,'max':max(vals),'zero_count':sum(v==0 for v in vals),'unique_count':u,'tie_observation_count':n-u}

distributions={'L':{},'private_establishments_2016':{}}
for g in groups:
    sub=group_rows(g)
    distributions['L'][g]={'raw_L':dist([r['floor_area_L_h24'] for r in sub]),'scaled_L':dist([r['execution_L_per_est_2016'] for r in sub])}
    distributions['private_establishments_2016'][g]=dist([r['private_establishments_2016'] for r in sub])

outcome_path=OUT/'age_growth_temporal_revalidation_2024_outcome_30regions.csv'
out_fields=['region_code','region_name','metro','floor_area_L_FY2024_apr_dec','floor_area_L_FY2024_jan_mar','floor_area_L_FY2024','floor_area_L_FY2025','floor_area_L_h24','execution_L_per_est_2016']
with outcome_path.open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=out_fields,lineterminator='\n'); w.writeheader()
    for r in rows: w.writerow({k:r[k] for k in out_fields})

eval_path=OUT/'age_growth_temporal_revalidation_2024_evaluation.csv'
eval_fields=['predictor','scaled_ALL','scaled_Sapporo','scaled_Kobe','scaled_Kyoto','raw_ALL','raw_Sapporo','raw_Kobe','raw_Kyoto','primary_pass','top5_overlap','top5_enrichment','top10_overlap','top10_enrichment','permutation_p_all_100k','partial_rank_log_est_city']
with eval_path.open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=eval_fields,lineterminator='\n'); w.writeheader(); w.writerow({
        'predictor':'age20_29_growth_2022_to_2023_pct',
        'scaled_ALL':scaled['ALL'],'scaled_Sapporo':scaled['Sapporo'],'scaled_Kobe':scaled['Kobe'],'scaled_Kyoto':scaled['Kyoto'],
        'raw_ALL':raw['ALL'],'raw_Sapporo':raw['Sapporo'],'raw_Kobe':raw['Kobe'],'raw_Kyoto':raw['Kyoto'],
        'primary_pass':str(primary_pass).lower(),'top5_overlap':topk['5']['overlap'],'top5_enrichment':topk['5']['enrichment'],'top10_overlap':topk['10']['overlap'],'top10_enrichment':topk['10']['enrichment'],'permutation_p_all_100k':permutation_p,'partial_rank_log_est_city':partial_rank})

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
verdict={
    'status':status,'interpretation':interpretation,
    'preregistration_commit':PREREG,'predictor_freeze_commit':PRED_FREEZE,'outcome_source_freeze_commit':SOURCE_FREEZE,
    'protocol':{'cutoff':'2024-03-31','answer_window':'2024-04-01..2026-03-31','regions':{'total':30,'Sapporo':10,'Kobe':9,'Kyoto':11},'predictor':'age20_29_growth_2022_to_2023_pct','rule':'PASS iff scaled Spearman is strictly positive in ALL, Sapporo, Kobe, and Kyoto.'},
    'outcome_source':period_meta,
    'result':{'scaled_spearman':scaled,'raw_spearman':raw,'primary_pass':primary_pass,'raw_conflict':raw_conflict},
    'diagnostics':{'permutations':PERMUTATIONS,'permutation_tail':'two-sided absolute Spearman','seed_source':'first_8_hex_of_preregistration_commit','seed':SEED,'permutation_p_all':permutation_p,'topk':topk,'topk_tie_break':'region_code ascending','partial_rank_log_est_city':partial_rank,'permutation_is_acceptance_condition':False},
    'distributions':distributions,
    'files':{'outcome_csv_sha256':sha(outcome_path),'evaluation_csv_sha256':sha(eval_path)},
    'next_constraint':'If PASS, temporal durability of the single mechanism is strengthened but no scalar is authorized. If FAIL, preserve the failure and cap the claim at the prior-window spatial replication.'
}
verdict_path=OUT/'age_growth_temporal_revalidation_2024_verdict.json'
verdict_path.write_text(json.dumps(verdict,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

result_path=OUT/'age20-29-growth-L-temporal-revalidation-result-2026-08-24.md'
result_path.write_text(f'''# Neighborhood Pulse — age20-29 growth -> L temporal revalidation result

Date: 2026-08-24

## Status

**{status}. No post-result tuning.**

Gates:
- preregistration: `{PREREG}`
- predictor freeze: `{PRED_FREEZE}`
- outcome-source-byte freeze: `{SOURCE_FREEZE}`
- same Sapporo 10 + Kobe 9 + Kyoto 11 = 30 wards
- predictor: `age20_29_growth_2022_to_2023_pct`
- cutoff/H24: 2024-03-31 / 2024-04-01..2026-03-31

## Primary result

| group | scaled L Spearman | raw L Spearman |
|---|---:|---:|
| ALL | {scaled['ALL']:.12f} | {raw['ALL']:.12f} |
| Sapporo | {scaled['Sapporo']:.12f} | {raw['Sapporo']:.12f} |
| Kobe | {scaled['Kobe']:.12f} | {raw['Kobe']:.12f} |
| Kyoto | {scaled['Kyoto']:.12f} | {raw['Kyoto']:.12f} |

Primary rule = **{'PASS' if primary_pass else 'FAIL'}** because {'all four scaled correlations are strictly positive' if primary_pass else 'at least one scaled city/group correlation is non-positive'}.

## Source validation

All three pre-frozen Building Starts files were SHA-verified before parsing. The L floor-area column was identified from header semantics (`不動産業` + `床面積`), not from outcome values. For every source period, ward sums equal the corresponding Sapporo/Kobe/Kyoto city totals. Missing/suppressed/non-numeric target values cause failure; no zero fill is used.

## Diagnostics

- deterministic 100k two-sided permutation p(ALL): `{permutation_p}`
- top5 overlap/enrichment: `{topk['5']['overlap']}` / `{topk['5']['enrichment']}x`
- top10 overlap/enrichment: `{topk['10']['overlap']}` / `{topk['10']['enrichment']}x`
- rank-residual diagnostic after log(2016 establishments)+city: `{partial_rank}`
- raw conflict: `{raw_conflict}`

## Interpretation

{'The single age20-29 growth -> L mechanism survives a later temporal window on the same untouched 30-ward universe, strengthening temporal durability evidence. This still does not rehabilitate the failed five-feature Demand family or authorize a scalar.' if primary_pass else 'The single age20-29 growth -> L mechanism does not survive the later temporal gate as preregistered. Preserve the prior spatial replication as period-specific evidence; do not retune the predictor, cities, denominator, L head, or H24 window to rescue this result.'}
''',encoding='utf-8')
print(json.dumps(verdict,ensure_ascii=False,indent=2))
