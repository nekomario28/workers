import csv
import hashlib
import json
import math
from pathlib import Path

import openpyxl
import xlrd

OUT = Path('/tmp/out')
OUT.mkdir(parents=True, exist_ok=True)

FRESH_REGIONS = [
    ('01101','札幌市中央区','Sapporo'),('01102','札幌市北区','Sapporo'),
    ('01103','札幌市東区','Sapporo'),('01104','札幌市白石区','Sapporo'),
    ('01105','札幌市豊平区','Sapporo'),('01106','札幌市南区','Sapporo'),
    ('01107','札幌市西区','Sapporo'),('01108','札幌市厚別区','Sapporo'),
    ('01109','札幌市手稲区','Sapporo'),('01110','札幌市清田区','Sapporo'),
    ('28101','神戸市東灘区','Kobe'),('28102','神戸市灘区','Kobe'),
    ('28105','神戸市兵庫区','Kobe'),('28106','神戸市長田区','Kobe'),
    ('28107','神戸市須磨区','Kobe'),('28108','神戸市垂水区','Kobe'),
    ('28109','神戸市北区','Kobe'),('28110','神戸市中央区','Kobe'),
    ('28111','神戸市西区','Kobe'),
    ('26101','京都市北区','Kyoto'),('26102','京都市上京区','Kyoto'),
    ('26103','京都市左京区','Kyoto'),('26104','京都市中京区','Kyoto'),
    ('26105','京都市東山区','Kyoto'),('26106','京都市下京区','Kyoto'),
    ('26107','京都市南区','Kyoto'),('26108','京都市右京区','Kyoto'),
    ('26109','京都市伏見区','Kyoto'),('26110','京都市山科区','Kyoto'),
    ('26111','京都市西京区','Kyoto'),
]
SPATIAL_CODES = [
    *[(c, 'Osaka') for c in ['27102','27103','27104','27106','27107','27108','27109','27111','27113','27114','27115','27116','27117','27118','27119','27120','27121','27122','27123','27124','27125','27126','27127','27128']],
    *[(f'231{i:02d}', 'Nagoya') for i in range(1,17)],
]
if len(FRESH_REGIONS) != 30 or len(SPATIAL_CODES) != 40:
    raise SystemExit('invalid frozen region sets')


def code5(v):
    s = str(v or '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s[:5] if len(s) >= 5 and s[:5].isdigit() else None


def load_age_rows(path):
    p = Path(path)
    blob = p.read_bytes()
    if blob[:4] == b'PK\x03\x04':
        wb = openpyxl.load_workbook(p, data_only=True, read_only=True)
        ws = wb.worksheets[0]
        return [tuple(r) for r in ws.iter_rows(values_only=True)], 'OOXML'
    if blob[:8] == bytes.fromhex('D0CF11E0A1B11AE1'):
        wb = xlrd.open_workbook(file_contents=blob)
        sh = wb.sheet_by_index(0)
        return [tuple(sh.row_values(i)) for i in range(sh.nrows)], 'BIFF8/OLE'
    raise SystemExit(f'unknown excel signature {p.name} {blob[:8]!r}')


def age_rows(rows, targets):
    out = {}
    for row in rows:
        if len(row) <= 10:
            continue
        c = code5(row[0])
        if c not in targets:
            continue
        sex = str(row[3] or '').strip()
        if sex != '計':
            continue
        if c in out:
            raise SystemExit(f'duplicate age total row {c}')
        total = float(row[4])
        a20 = float(row[9])
        a25 = float(row[10])
        out[c] = {'total': total, 'age20_29': a20 + a25}
    return out


temporal_refs = {
    '13101': 0.48237050648902713,
    '13108': 2.687494452826833,
    '40133': 1.9956887559974934,
    '40135': -1.2308521629756042,
}
all_age_targets = {c for c,_,_ in FRESH_REGIONS} | {c for c,_ in SPATIAL_CODES} | set(temporal_refs)
rows20, fmt20 = load_age_rows('/tmp/demand/2020_age.xls')
rows21, fmt21 = load_age_rows('/tmp/demand/2021_age.xlsx')
a20 = age_rows(rows20, all_age_targets)
a21 = age_rows(rows21, all_age_targets)
missing20 = sorted(all_age_targets - set(a20))
missing21 = sorted(all_age_targets - set(a21))
if missing20 or missing21:
    raise SystemExit(f'age coverage mismatch 2020={missing20} 2021={missing21}')


def growth(code):
    old = a20[code]['age20_29']
    new = a21[code]['age20_29']
    if old == 0:
        raise SystemExit(f'zero 2020 age20_29 {code}')
    return (new / old - 1.0) * 100.0


ref_errors = {c: abs(growth(c) - v) for c,v in temporal_refs.items()}
if max(ref_errors.values()) > 1e-10:
    detail = {c: {'got': growth(c), 'expected': v, 'error': ref_errors[c]} for c,v in temporal_refs.items()}
    raise SystemExit('original temporal transform reproduction failed ' + json.dumps(detail, ensure_ascii=False))

corrected_spatial = [(c, metro, growth(c)) for c,metro in SPATIAL_CODES]
fresh_pred = [(c,name,metro,growth(c)) for c,name,metro in FRESH_REGIONS]

DENOM_REFS = {'27102':4981,'27128':31316,'23101':7324,'23106':20983}
targets = {c for c,_,_ in FRESH_REGIONS} | set(DENOM_REFS)
wb = xlrd.open_workbook('/tmp/denom/table1.xls', on_demand=True)
candidates = []
for sidx in range(wb.nsheets):
    sh = wb.sheet_by_index(sidx)
    rows = {}
    for i in range(sh.nrows):
        found = None
        for j in range(min(8, sh.ncols)):
            c = code5(sh.cell_value(i,j))
            if c in targets:
                found = c
                break
        if found:
            rows[found] = i
    if not set(DENOM_REFS).issubset(rows):
        continue
    for col in range(sh.ncols):
        ok = True
        for code,val in DENOM_REFS.items():
            try:
                num = float(str(sh.cell_value(rows[code],col)).replace(',',''))
            except Exception:
                ok = False
                break
            if abs(num - val) > 1e-9:
                ok = False
                break
        if ok:
            candidates.append((sidx,col,rows))
if len(candidates) != 1:
    raise SystemExit('denominator reference column not unique: ' + repr([(a,b) for a,b,_ in candidates]))
sidx,col,rows = candidates[0]
sh = wb.sheet_by_index(sidx)
fresh_denom = []
for code,name,metro in FRESH_REGIONS:
    if code not in rows:
        raise SystemExit('missing denominator row ' + code)
    val = int(round(float(str(sh.cell_value(rows[code],col)).replace(',',''))))
    if val <= 0:
        raise SystemExit('invalid denominator ' + code)
    fresh_denom.append((code,name,metro,val))
denominator_sheet = sh.name
wb.release_resources()

p_corr = OUT/'age_growth_spatial_holdout_2022_corrected_40regions.csv'
with p_corr.open('w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['region_code','metro','age20_29_growth_2020_to_2021_pct_corrected'])
    w.writerows(corrected_spatial)

p_pred = OUT/'age_growth_fresh_spatial_holdout_2022_predictor_30regions.csv'
with p_pred.open('w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['region_code','region_name','metro','age20_29_growth_2020_to_2021_pct'])
    w.writerows(fresh_pred)

p_den = OUT/'establishments_2016_age_growth_fresh_spatial_holdout_30regions.csv'
with p_den.open('w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['region_code','region_name','metro','private_establishments_2016'])
    w.writerows(fresh_denom)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

meta = {
    'status': 'CORRECTION_AUDIT_AND_FRESH_SOURCE_FREEZE_BEFORE_OUTCOME',
    'canonical_preregistration_boundary': 'f6b8e89d55f29f5f637fd52a58a08f598c8b7ff2',
    'original_temporal_source_run': 32596779351,
    'original_temporal_source_job': 97088922150,
    'transport_repository': 'nekomario28/workers',
    'source_artifact_ids': {'demand':9481762001,'denominator':9480653606},
    'source_sha256': {
        '2020_age':'481c335fe5e5458c7751aec403c289e55cfeb3d0e2a81cc789eb043c00a21c0b',
        '2021_age':'af485797942888ae6d6b6bc0d1777e791e8715cba5d83c3b117cec0fc6eac394',
        'denominator_2016':'73249e927cf4363b375b2fbdafc6d5c2466c566998cba4844b3c5b505c6cd35b',
    },
    'transform': 'exact original age_rows semantics: code=row[0][:5], sex=row[3]==計, age20_29=row[9]+row[10], growth=(2021/2020-1)*100',
    'source_formats': {'2020_age':fmt20,'2021_age':fmt21},
    'validation': {
        'temporal_reference_checks': temporal_refs,
        'temporal_reference_max_abs_error': max(ref_errors.values()),
        'denominator_reference_checks': DENOM_REFS,
        'denominator_sheet': denominator_sheet,
        'denominator_column_zero_based': col,
    },
    'files': {p_corr.name:sha(p_corr),p_pred.name:sha(p_pred),p_den.name:sha(p_den)},
    'fresh_outcome_retrieved': False,
    'zero_fill': False,
}
p_meta = OUT/'age_growth_fresh_spatial_holdout_2022_source_freeze_meta.json'
p_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(meta, ensure_ascii=False, indent=2))
