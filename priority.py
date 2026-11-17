"""Explainable, normalized prototype scoring. Not a validated engineering assessment."""
from datetime import datetime, timezone

def clamp(x):
    return max(0, min(100, float(x)))

def band(value):
    return 'CRITICAL' if value >= 80 else 'HIGH' if value >= 60 else 'MEDIUM' if value >= 40 else 'LOW'

def severity_estimate(area_fraction, traffic=50, speed=40, road_importance=50, sensitive_location=0, reports=1):
    # Screen area is only a rough proxy for size; other values are illustrative defaults.
    size = clamp(area_fraction * 900)
    return round(clamp(size*.55 + clamp(traffic)*.12 + clamp(speed)*.08 + clamp(road_importance)*.10 + clamp(sensitive_location)*.08 + clamp(reports*10)*.07))

def priority(report):
    try:
        timestamp = datetime.fromisoformat(report['timestamp'].replace('Z','+00:00'))
        days = max(0, (datetime.now(timezone.utc) - timestamp).total_seconds()/86400)
    except (KeyError, ValueError, TypeError):
        days = 0
    components = {'severity': clamp(report.get('severity_score', 40)), 'traffic': clamp(report.get('traffic',50)), 'road_importance': clamp(report.get('road_importance',50)), 'sensitive_location': clamp(report.get('sensitive_location',0)), 'citizen_reports': clamp(report.get('citizen_reports', report.get('reports',1) if report.get('source') in ('citizen','demo') else 0)*10), 'damage_age': clamp(days*5)}
    score = round(components['severity']*.4 + components['traffic']*.2 + components['road_importance']*.15 + components['sensitive_location']*.1 + components['citizen_reports']*.1 + components['damage_age']*.05)
    return score, components

def decorate(r):
    r = dict(r)
    r.setdefault('sources', [r.get('source', 'unknown')])
    r.setdefault('citizen_reports', r.get('reports', 1) if r.get('source') in ('citizen', 'demo') else 0)
    r['severity_score'] = round(clamp(r.get('severity_score', 40)))
    r['severity'] = band(r['severity_score'])
    r['priority'], r['priority_components'] = priority(r)
    r['priority_band'] = band(r['priority'])
    return r

def deterioration(reports):
    active = [r for r in reports if r.get('status') != 'Repaired']
    if not active: return {'score': 0, 'label': 'LOW', 'action': 'Continue routine monitoring', 'health': 100, 'health_label': 'GOOD'}
    avg = lambda key, default: sum(float(r.get(key, default)) for r in active)/len(active)
    # Demo inputs: rainfall and road age are illustrative assumptions, not sensor observations.
    repair_gap = 100 * (1 - sum(r.get('status') == 'Repaired' for r in reports) / max(1, len(reports)))
    score = round(clamp(avg('severity_score', 0)*.30 + avg('traffic',50)*.20 + 65*.15 + 55*.15 + repair_gap*.10 + min(avg('citizen_reports',0)*10,100)*.10))
    health = round(clamp(100 - (avg('severity_score',0)*.45 + min(len(active)*3,25))))
    return {'score':score,'label':band(score),'action': 'Inspect within 7 days' if score >= 60 else 'Schedule routine inspection','health':health,'health_label':'GOOD' if health>=80 else 'FAIR' if health>=60 else 'POOR' if health>=40 else 'CRITICAL'}


def road_segments(reports):
    groups={}
    for r in reports:
        key=r.get('location','Unknown location').strip() or 'Unknown location'
        groups.setdefault(key,[]).append(r)
    rows=[]
    for name, group in groups.items():
        active=[r for r in group if r.get('status')!='Repaired']
        penalty=0 if not active else min(100, sum(r['severity_score'] for r in active)/len(active)*.6 + min(20,len(active)*5))
        health=round(100-penalty)
        rows.append({'location':name,'health':health,'label':'GOOD' if health>=80 else 'FAIR' if health>=60 else 'POOR' if health>=40 else 'CRITICAL','active':len(active),'total':len(group),'risk':deterioration(group)['score']})
    return sorted(rows,key=lambda r:(r['health'],r['location']))
