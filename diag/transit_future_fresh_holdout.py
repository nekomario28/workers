import csv, hashlib, heapq, io, itertools, json, math, unicodedata, zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests, shapefile

GAP=Path('input/transit_future_gap_universe_2014_strict.csv')
GAP_SHA='d9b36d5cb2b08a58e0e95f3efa44a85eda0ffd5bd1b393252f437cba42fcf367'
BASE_YEAR=2014
BASE_SHA='a8a6dd8b00bb175ca89cd0ac542312b3726cbd81ced06a1d85ae0a6098e56204'
WASHOUT_YEAR=2015
ANSWER_YEARS=range(2016,2021)
END_YEAR=2020
POP_STATS='T000609'
POP_FIELD='T000609001'
SNAP=5
SPECIAL={'大船渡線','気仙沼線'}

if hashlib.sha256(GAP.read_bytes()).hexdigest()!=GAP_SHA:
    raise SystemExit('2014 frozen gap SHA mismatch')
rows=list(csv.DictReader(GAP.open(encoding='utf-8')))
if len(rows)!=9737:
    raise SystemExit(f'expected 9737 frozen gaps, got {len(rows)}')

def norm(x): return ''.join(unicodedata.normalize('NFKC',str(x or '')).split())
def hav(lat1,lon1,lat2,lon2):
    R=6371000.; p1=math.radians(lat1); p2=math.radians(lat2)
    dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(min(1,math.sqrt(a)))
def centroid(shape):
    pts=shape.points
    return (sum(p[1] for p in pts)/len(pts),sum(p[0] for p in pts)/len(pts)) if pts else (None,None)
def parts(shape):
    pts=shape.points; starts=list(shape.parts)+[len(pts)]
    return [pts[starts[i]:starts[i+1]] for i in range(len(starts)-1) if starts[i+1]-starts[i]>=1]
def node(p): return (round(p[0],SNAP),round(p[1],SNAP))

def fetch_n02(year):
    yy=str(year)[-2:]
    urls=[f'https://nlftp.mlit.go.jp/ksj/gml/data/N02/N02-{yy}/N02-{yy}_GML.zip',f'https://nlftp.mlit.go.jp/ksj/gml/data/N02/N02-{yy}/N02-{yy}.zip']
    for u in urls:
        q=requests.get(u,headers={'User-Agent':'Mozilla/5.0'},timeout=120)
        if q.status_code==200 and q.content[:2]==b'PK': return u,q.content
    raise RuntimeError(f'N02-{year} download failed')

def shp_reader(raw,token):
    z=zipfile.ZipFile(io.BytesIO(raw)); names=z.namelist()
    cands=sorted([n for n in names if n.lower().endswith(token.lower()+'.shp')],key=lambda n:(0 if '/utf-8/' in n.lower() else 1,n))
    errs=[]
    for shp in cands:
        base=shp[:-4]; fs={e:next((n for n in names if n.lower()==(base+e).lower()),None) for e in ['.shp','.shx','.dbf']}
        if not all(fs.values()): continue
        for enc in (['utf-8','cp932'] if '/utf-8/' in shp.lower() else ['cp932','utf-8']):
            try:
                r=shapefile.Reader(shp=io.BytesIO(z.read(fs['.shp'])),shx=io.BytesIO(z.read(fs['.shx'])),dbf=io.BytesIO(z.read(fs['.dbf'])),encoding=enc,encodingErrors='strict')
                if len(r): _=r.record(0)
                return r,shp,enc
            except Exception as e: errs.append((shp,enc,repr(e)))
    raise RuntimeError(f'cannot read {token}: {errs[:4]}')

def station_records(raw,keep_shapes=False):
    sr,sname,senc=shp_reader(raw,'Station'); fields=[f[0] for f in sr.fields[1:]]
    if not {'N02_003','N02_004','N02_005'}.issubset(fields): raise RuntimeError(f'station schema {fields}')
    by=defaultdict(list)
    for idx,rec in enumerate(sr.iterShapeRecords()):
        d=dict(zip(fields,rec.record)); op=norm(d.get('N02_004')); line=norm(d.get('N02_003')); name=norm(d.get('N02_005'))
        if not op or not line or not name or not rec.shape.points: continue
        lat,lon=centroid(rec.shape); x={'name':name,'lat':lat,'lon':lon,'record_index':idx}
        if keep_shapes: x['shape']=rec.shape
        by[(op,line)].append(x)
    return by,(sname,senc,len(sr))

def group_stations(by):
    out={}
    for service,recs in by.items():
        groups=[]
        for x in sorted(recs,key=lambda r:(r['name'],r['lat'],r['lon'],r['record_index'])):
            hit=None
            for g in groups:
                if g['name']==x['name'] and hav(g['lat'],g['lon'],x['lat'],x['lon'])<=300:
                    hit=g; break
            if hit is None:
                hit={'name':x['name'],'lat':x['lat'],'lon':x['lon'],'members':[],'nodes':set()}; groups.append(hit)
            hit['members'].append(x)
            n=len(hit['members']); hit['lat']=sum(m['lat'] for m in hit['members'])/n; hit['lon']=sum(m['lon'] for m in hit['members'])/n
        groups.sort(key=lambda g:(g['name'],g['lat'],g['lon']))
        for i,g in enumerate(groups): g['gid']=i
        out[service]=groups
    return out

# Exact cutoff network.
u14,b14=fetch_n02(BASE_YEAR); sha14=hashlib.sha256(b14).hexdigest()
if sha14!=BASE_SHA: raise SystemExit(f'N02-2014 raw SHA changed: {sha14}')
base_raw,station_meta=station_records(b14,keep_shapes=True); base=group_stations(base_raw)
rr,rname,renc=shp_reader(b14,'RailroadSection'); rf=[f[0] for f in rr.fields[1:]]
rail_shapes=defaultdict(list)
for rec in rr.iterShapeRecords():
    d=dict(zip(rf,rec.record)); service=(norm(d.get('N02_004')),norm(d.get('N02_003')))
    if service[0] and service[1] and rec.shape.points: rail_shapes[service].append(rec.shape)

# Exact cutoff graph, same topology thresholds as preregistration.
graphs={}; owners={}; graph_nodes={}
for service,groups in base.items():
    adj=defaultdict(dict)
    def add_shape(sh):
        for pp in parts(sh):
            for a,b in zip(pp,pp[1:]):
                na=node(a); nb=node(b)
                if na==nb: continue
                d=hav(na[1],na[0],nb[1],nb[0]); old=adj[na].get(nb)
                if old is None or d<old: adj[na][nb]=d; adj[nb][na]=d
    for sh in rail_shapes.get(service,[]): add_shape(sh)
    for g in groups:
        for m in g['members']:
            add_shape(m['shape'])
            for pp in parts(m['shape']):
                for p in pp: g['nodes'].add(node(p))
    nodes=list(adj)
    for g in groups:
        good={n for n in g['nodes'] if n in adj}
        if not good and nodes:
            best=min(nodes,key=lambda n:hav(g['lat'],g['lon'],n[1],n[0]))
            if hav(g['lat'],g['lon'],best[1],best[0])<=50: good={best}
        g['nodes']=good
    owner=defaultdict(set)
    for g in groups:
        for n in g['nodes']: owner[n].add(g['gid'])
    graphs[service]=adj; owners[service]=owner; graph_nodes[service]=nodes

# Resolve frozen CSV gaps back to physical cutoff station groups.
gap_pair={}; gap_internal={}; unresolved=[]
for r in rows:
    service=(norm(r['operator']),norm(r['line'])); groups=base.get(service,[])
    A=[g for g in groups if g['name']==norm(r['station_a'])]; B=[g for g in groups if g['name']==norm(r['station_b'])]
    best=None
    for ga in A:
        for gb in B:
            if ga['gid']==gb['gid']: continue
            ml=(ga['lat']+gb['lat'])/2; mn=(ga['lon']+gb['lon'])/2
            d=hav(ml,mn,float(r['endpoint_centroid_lat']),float(r['endpoint_centroid_lon']))
            if best is None or d<best[0]: best=(d,ga,gb)
    if best is None or best[0]>500:
        unresolved.append((r['gap_id'],service,r['station_a'],r['station_b'],None if best is None else best[0])); continue
    ga,gb=best[1],best[2]; k=(service,frozenset((ga['gid'],gb['gid'])))
    if k in gap_pair: raise SystemExit(f'duplicate physical gap mapping {k}')
    gap_pair[k]=r['gap_id']; gap_internal[r['gap_id']]={'service':service,'a':ga,'b':gb}
if unresolved: raise SystemExit(f'unresolved frozen gap endpoints {unresolved[:10]} count={len(unresolved)}')
if len(gap_internal)!=len(rows): raise SystemExit('gap endpoint resolution count mismatch')

baseline_names={service:{g['name'] for g in groups} for service,groups in base.items()}

def same_identity(g,arr,threshold=500):
    return any(x['name']==g['name'] and hav(x['lat'],x['lon'],g['lat'],g['lon'])<=threshold for x in arr)

def map_to_cutoff_gap(service,cand):
    groups=base.get(service); adj=graphs.get(service); owner=owners.get(service); nodes=graph_nodes.get(service)
    if not groups or not adj or not nodes: return [],'no_cutoff_service'
    nearest_existing=min(hav(cand['lat'],cand['lon'],g['lat'],g['lon']) for g in groups)
    if nearest_existing<=300: return [],'near_existing_station'
    nearest=min(nodes,key=lambda n:hav(cand['lat'],cand['lon'],n[1],n[0])); nd=hav(cand['lat'],cand['lon'],nearest[1],nearest[0])
    if nd>100: return [],'off_cutoff_geometry'
    dist={nearest:0.}; heap=[(0.,nearest)]; found={}
    while heap:
        d,u=heapq.heappop(heap)
        if d!=dist.get(u): continue
        gids=list(owner.get(u,()))
        if gids:
            for gid in gids:
                if gid not in found: found[gid]=d
            continue
        for v,w in adj.get(u,{}).items():
            z=d+w
            if z<dist.get(v,float('inf')):
                dist[v]=z; heapq.heappush(heap,(z,v))
    matches=[]
    for a,b in itertools.combinations(sorted(found),2):
        k=(service,frozenset((a,b)))
        if k in gap_pair: matches.append(gap_pair[k])
    matches=sorted(set(matches))
    return matches,'mapped' if len(matches)==1 else ('ambiguous' if matches else 'no_adjacent_gap')

# Fresh answer snapshots, opened only after preregistration commit.
future={}; source_manifest=[]
for y in range(WASHOUT_YEAR,END_YEAR+1):
    u,b=fetch_n02(y); by,meta=station_records(b,keep_shapes=False); future[y]=group_stations(by)
    source_manifest.append({'year':y,'url':u,'sha256':hashlib.sha256(b).hexdigest(),'station_source':meta[0],'encoding':meta[1],'station_records':meta[2]})
Path('out/n02_future_source_manifest_2015_2020.json').write_text(json.dumps(source_manifest,ensure_ascii=False,indent=2),encoding='utf-8')

seen_future=defaultdict(list); addition_audit=[]
washout=defaultdict(list); positives=defaultdict(list); semantic_censor=defaultdict(list); ambiguous_gaps=set(); reason_counts=Counter()
for y in range(WASHOUT_YEAR,END_YEAR+1):
    for service,groups in sorted(future[y].items()):
        baseline=base.get(service,[])
        for g in groups:
            if same_identity(g,baseline,500): continue
            if same_identity(g,seen_future[service],500): continue
            seen_future[service].append({'name':g['name'],'lat':g['lat'],'lon':g['lon']})
            matches,reason=map_to_cutoff_gap(service,g); reason_counts[reason]+=1
            same_name_preexisting=g['name'] in baseline_names.get(service,set())
            rec={'first_snapshot_year':y,'operator':service[0],'line':service[1],'station_name':g['name'],'lat':g['lat'],'lon':g['lon'],'mapping_reason':reason,'matched_gap_ids':'|'.join(matches),'preexisting_same_name_on_cutoff_service':same_name_preexisting}
            addition_audit.append(rec)
            if len(matches)==1:
                gid=matches[0]
                if same_name_preexisting: semantic_censor[gid].append(rec)
                elif y==WASHOUT_YEAR: washout[gid].append(rec)
                else: positives[gid].append(rec)
            elif len(matches)>1:
                ambiguous_gaps.update(matches)

future_end=future[END_YEAR]
def endpoint_survives(service,g): return same_identity(g,future_end.get(service,[]),500)

statuses=Counter(); enriched=[]
for r in rows:
    gid=r['gap_id']; x=gap_internal[gid]
    special=str(r['official_brt_special_mode_excluded']).lower()=='true' or norm(r['line']) in SPECIAL
    if special: status='special_mode_excluded'
    elif gid in semantic_censor: status='censored_preexisting_same_name_relocation_or_recode'
    elif gid in washout: status='washout_2015_addition'
    elif gid in ambiguous_gaps: status='censored_ambiguous_future_addition'
    elif gid in positives: status='positive'
    elif endpoint_survives(x['service'],x['a']) and endpoint_survives(x['service'],x['b']): status='negative'
    else: status='censored_service_or_endpoint_change'
    statuses[status]+=1
    z=dict(r); z['fresh_label_status']=status
    z['fresh_first_positive_snapshot_year']=min((a['first_snapshot_year'] for a in positives.get(gid,[])),default='')
    z['fresh_positive_station_names']='|'.join(sorted({a['station_name'] for a in positives.get(gid,[])}))
    z['fresh_washout_station_names']='|'.join(sorted({a['station_name'] for a in washout.get(gid,[])}))
    z['fresh_semantic_censor_station_names']='|'.join(sorted({a['station_name'] for a in semantic_censor.get(gid,[])}))
    enriched.append(z)

# Correct implementation of intended 2010 Census 3x3 500m neighborhood.
BASEPOP='https://www.e-stat.go.jp/gis/statmap-search/data'
def mesh500_code(lat,lon):
    p=int(math.floor(lat*1.5)); q=int(math.floor(lon))-100; lat1=lat*1.5-p; lon1=lon-math.floor(lon)
    rr=int(math.floor(lat1*8)); s=int(math.floor(lon1*8)); lat2=lat1*8-rr; lon2=lon1*8-s
    t=int(math.floor(lat2*10)); u=int(math.floor(lon2*10)); lat3=lat2*10-t; lon3=lon2*10-u
    hrow=1 if lat3>=0.5 else 0; hcol=1 if lon3>=0.5 else 0; h=1+hcol+2*hrow
    return f'{p:02d}{q:02d}{rr}{s}{t}{u}{h}'
def mesh500_center(code):
    p=int(code[:2]); q=int(code[2:4]); rr=int(code[4]); s=int(code[5]); t=int(code[6]); u=int(code[7]); h=int(code[8])
    hrow=1 if h in (3,4) else 0; hcol=1 if h in (2,4) else 0
    lat=p/1.5+rr*(5/60)+t*(30/3600)+hrow*(15/3600)+(7.5/3600)
    lon=q+100+s*(7.5/60)+u*(45/3600)+hcol*(22.5/3600)+(11.25/3600)
    return lat,lon
def neighbors9(code):
    lat,lon=mesh500_center(code)
    return [mesh500_code(lat+dy*(15/3600),lon+dx*(22.5/3600)) for dy in (-1,0,1) for dx in (-1,0,1)]

required=set()
for r in enriched:
    c=mesh500_code(float(r['endpoint_centroid_lat']),float(r['endpoint_centroid_lon']))
    for n in neighbors9(c): required.add(n[:4])

def fetch_pop(code):
    s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0','Referer':'https://www.e-stat.go.jp/gis/statmap-search'})
    q=s.get(BASEPOP,params={'statsId':POP_STATS,'code':code,'downloadType':'2'},timeout=120); q.raise_for_status()
    if q.content[:2]!=b'PK': raise RuntimeError(f'{code}: population not zip')
    z=zipfile.ZipFile(io.BytesIO(q.content)); ns=[n for n in z.namelist() if n.lower().endswith(('.txt','.csv'))]
    if len(ns)!=1: raise RuntimeError(f'{code}: population files {z.namelist()}')
    b=z.read(ns[0]); rd=list(csv.reader(io.StringIO(b.decode('cp932'))))
    if len(rd)<2 or POP_FIELD not in rd[0]: raise RuntimeError(f'{code}: population schema {rd[:2]}')
    idx=rd[0].index(POP_FIELD); d={}; suppressed=0
    for a in rd[2:]:
        if not a or not a[0]: continue
        v=a[idx].strip() if len(a)>idx else ''
        if v in ('','*','X','-'): d[a[0]]=None; suppressed+=1
        else: d[a[0]]=int(float(v))
    return code,d,{'first_mesh':code,'raw_zip_sha256':hashlib.sha256(q.content).hexdigest(),'inner_sha256':hashlib.sha256(b).hexdigest(),'records':len(rd)-2,'suppressed_population_cells':suppressed}

pop={}; pmanifest=[]; errors=[]
with ThreadPoolExecutor(max_workers=8) as ex:
    fs={ex.submit(fetch_pop,c):c for c in sorted(required)}
    for i,f in enumerate(as_completed(fs),1):
        try:
            c,d,m=f.result(); pop.update(d); pmanifest.append(m)
            if i%10==0: print('POP_PROGRESS',i,'of',len(required))
        except Exception as e: errors.append((fs[f],repr(e)))
if errors: raise SystemExit(f'population download errors {errors}')
pmanifest.sort(key=lambda x:x['first_mesh'])
Path('out/population_source_manifest_2010.json').write_text(json.dumps(pmanifest,ensure_ascii=False,indent=2),encoding='utf-8')

missing_mid=supp_mid=missing_3=supp_3=0
for r in enriched:
    c=mesh500_code(float(r['endpoint_centroid_lat']),float(r['endpoint_centroid_lon'])); ns=neighbors9(c)
    if c not in pop:
        v500=None; missing_mid+=1
    else:
        v500=pop[c]
        if v500 is None: supp_mid+=1
    vals=[]; bad_missing=False; bad_supp=False
    for n in ns:
        if n not in pop: bad_missing=True
        elif pop[n] is None: bad_supp=True
        else: vals.append(pop[n])
    if bad_missing: missing_3+=1
    if bad_supp: supp_3+=1
    r['mesh500_code_2010']=c
    r['pop500_midpoint_2010']='' if v500 is None else v500
    r['pop3x3_2010']='' if bad_missing or bad_supp else sum(vals)

# Fixed preregistered evaluation.
evalrows=[r for r in enriched if r['fresh_label_status'] in ('positive','negative') and r['pop500_midpoint_2010']!='' and r['pop3x3_2010']!='']
y=[1 if r['fresh_label_status']=='positive' else 0 for r in evalrows]; P=sum(y); N=len(y)
if P<1: raise SystemExit('fresh holdout has zero clean positives; preserve artifact but no performance claim')

def rank01(vals):
    order=sorted(range(len(vals)),key=lambda i:vals[i]); ans=[0.0]*len(vals); i=0; n=len(vals)
    while i<n:
        j=i+1
        while j<n and vals[order[j]]==vals[order[i]]: j+=1
        q=0.5 if n==1 else ((i+j-1)/2)/(n-1)
        for k in range(i,j): ans[order[k]]=q
        i=j
    return ans
rg=rank01([math.log1p(float(r['gap_length_m'])) for r in evalrows])
r500=rank01([math.log1p(float(r['pop500_midpoint_2010'])) for r in evalrows])
r3=rank01([math.log1p(float(r['pop3x3_2010'])) for r in evalrows])
scores={'gap_only':rg,'pop500_only_diagnostic':r500,'pop3x3_only':r3,'fixed_equal_rank_gap_pop3x3':[0.5*a+0.5*b for a,b in zip(rg,r3)]}
keys=[(r['operator'],r['line'],r['station_a'],r['station_b']) for r in evalrows]
def ap_tie(score):
    groups={}
    for s,yy in zip(score,y):
        a=groups.setdefault(s,[0,0]); a[0]+=yy; a[1]+=1
    tp=seen=0; ap=0.
    for s in sorted(groups,reverse=True):
        pos,n=groups[s]; tp+=pos; seen+=n
        if pos: ap+=(pos/P)*(tp/seen)
    return ap
def top(score,k):
    k=min(k,N); idx=sorted(range(N),key=lambda i:(-score[i],keys[i]))[:k]; h=sum(y[i] for i in idx)
    return {'k':k,'hits':h,'precision':h/k if k else 0.,'recall':h/P}
metrics={}
for name,score in scores.items():
    metrics[name]={'average_precision_tie_group':ap_tie(score),'top17':top(score,17),'top50':top(score,50),'top100':top(score,100),'top1pct':top(score,max(1,int(N*.01))),'top5pct':top(score,max(1,int(N*.05))),'unique_scores':len(set(score))}
    print('METRIC',name,json.dumps(metrics[name],ensure_ascii=False))

out=Path('out/transit_future_fresh_2014_2020_pop2010.csv')
with out.open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(enriched[0].keys())); w.writeheader(); w.writerows(enriched)
with open('out/future_addition_mapping_audit_2015_2020.csv','w',encoding='utf-8',newline='') as f:
    fs=['first_snapshot_year','operator','line','station_name','lat','lon','mapping_reason','matched_gap_ids','preexisting_same_name_on_cutoff_service']; w=csv.DictWriter(f,fieldnames=fs); w.writeheader(); w.writerows(addition_audit)

summary={
    'interpretation':'fresh temporal holdout; rules and corrected intended 3x3 implementation frozen before N02-2015..2020 outcomes were opened',
    'cutoff':'2015-08-01','predictor_network':'N02-2014 state 2014-12-31, HTTP Last-Modified 2015-07-16','washout':'N02-2015 mapped additions',
    'positive_answer':'first clean same-service existing-line infill appearing in N02-2016..N02-2020','negative':'no positive/washout/semantic/ambiguous event and both cutoff endpoints survive same service/name within 500m in N02-2020',
    'topology_threshold_m':100,'same_name_continuity_m':500,'same_name_station_group_m':300,
    'semantic_rule':'future station name already exists anywhere on cutoff operator+line => censor relocation/recode',
    'population_source':'2010 Census 500m T000609 / H002005112010, published 2013-06-11','population_field':'T000609001','population_neighborhood':'corrected midpoint cell + 8 adjacent 500m cells; missing/suppressed censored, no zero-fill',
    'fixed_combo_formula':'0.5 * percentile_rank(log1p(gap_length_m)) + 0.5 * percentile_rank(log1p(pop3x3_2010))',
    'gap_sha256':GAP_SHA,'n02_2014_sha256':sha14,'gap_count':len(rows),'status_counts':dict(statuses),'future_addition_mapping_reasons':dict(reason_counts),
    'evaluation_rows':N,'positives':P,'prevalence':P/N,'population_first_mesh_files':len(required),'population_missing_midpoint_rows':missing_mid,'population_suppressed_midpoint_rows':supp_mid,'population_missing_3x3_rows':missing_3,'population_suppressed_3x3_rows':supp_3,'metrics':metrics,'output_csv_sha256':hashlib.sha256(out.read_bytes()).hexdigest()
}
sp=Path('out/fresh_holdout_summary.json'); sp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print('GATE',json.dumps(summary,ensure_ascii=False))
print('POSITIVE_EXAMPLES')
for r in enriched:
    if r['fresh_label_status']=='positive': print(r['gap_id'],r['operator'],r['line'],r['station_a'],'--',r['station_b'],'=>',r['fresh_positive_station_names'],r['fresh_first_positive_snapshot_year'])
print('SEMANTIC_CENSORS')
for r in enriched:
    if r['fresh_label_status']=='censored_preexisting_same_name_relocation_or_recode': print(r['gap_id'],r['operator'],r['line'],r['station_a'],'--',r['station_b'],'=>',r['fresh_semantic_censor_station_names'])
for p in sorted(Path('out').iterdir()): print('SHA',p.name,hashlib.sha256(p.read_bytes()).hexdigest())
