import json, os, threading, uuid, math
from datetime import datetime, timezone, timedelta
from priority import decorate

PATH = os.environ.get('ROADGUARD_DATA', os.path.join(os.path.dirname(__file__), 'data', 'reports.json'))
lock = threading.RLock()
TYPES = ['POTHOLE', 'CRACK', 'ROAD DAMAGE', 'OPEN MANHOLE', 'ROAD EDGE DAMAGE']
STATUSES = ['Detected', 'Verified', 'Assigned', 'In Progress', 'Repaired']

def now(): return datetime.now(timezone.utc).isoformat()

def seed():
    roads = [
      ('Anna Nagar Main Road',9.9305,78.1475,'POTHOLE',96,95,95,100,17,'Detected'),
      ('K.K. Nagar Junction',9.9360,78.1506,'OPEN MANHOLE',90,92,90,100,12,'Verified'),
      ('Goripalayam Road',9.9325,78.1309,'POTHOLE',82,86,88,80,9,'Assigned'),
      ('Alagarkoil Main Road',9.9446,78.1585,'ROAD DAMAGE',73,80,85,40,7,'In Progress'),
      ('Vaigai River Road',9.9235,78.1322,'CRACK',58,61,62,30,4,'Detected'),
      ('Lake View Road',9.9206,78.1501,'ROAD EDGE DAMAGE',42,42,45,20,2,'Verified'),
      ('East Veli Street',9.9199,78.1279,'POTHOLE',33,35,40,0,1,'Repaired')]
    result=[]
    for i,(name,lat,lng,typ,sev,traffic,importance,sensitive,count,status) in enumerate(roads):
      result.append({'id':f'RG-{1040+i}', 'latitude':lat,'longitude':lng,'location':name,'timestamp':(datetime.now(timezone.utc)-timedelta(days=6-i%6)).isoformat(),'damage_type':typ,'confidence':min(99, 78+i*3),'severity_score':sev,'traffic':traffic,'road_importance':importance,'sensitive_location':sensitive,'reports':count,'citizen_reports':count,'status':status,'description':'Illustrative sample record for demonstration.','source':'demo','team':'Road Maintenance Unit 04' if status in ('Assigned','In Progress') else '', 'eta':'2 days' if status in ('Assigned','In Progress') else '', 'history':[{'timestamp':(datetime.now(timezone.utc)-timedelta(days=6-i%6)).isoformat(), 'message':'Simulated record created'}]})
    return result

def initialize():
    os.makedirs(os.path.dirname(PATH),exist_ok=True)
    with lock:
      if not os.path.exists(PATH): save(seed())

def save(items):
    with lock:
      tmp=PATH+'.tmp'
      with open(tmp,'w',encoding='utf8') as f: json.dump(items,f,indent=2)
      os.replace(tmp,PATH)

def get_raw():
    with lock:
      initialize()
      try:
        with open(PATH,encoding='utf8') as f: return json.load(f)
      except (OSError,ValueError): return []

def all_reports(): return [decorate(x) for x in get_raw()]

def distance(a,b,c,d):
    # Haversine metres
    p1,p2=math.radians(a),math.radians(c); dp=math.radians(c-a); dl=math.radians(d-b)
    h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 12742000*math.asin(min(1,math.sqrt(h)))

def event(record, message):
    record.setdefault('history', []).append({'timestamp': now(), 'message': str(message)[:200]})
    record['history'] = record['history'][-40:]
    record['updated_at'] = now()

def add(data):
    with lock:
      items=get_raw()
      # Separate demo and genuine records; group matching types within 75m.
      for r in items:
        if r['status']!='Repaired' and r['damage_type']==data['damage_type'] and (r.get('source')=='demo') == (data.get('source')=='demo') and distance(r['latitude'],r['longitude'],data['latitude'],data['longitude'])<75:
          r.setdefault('citizen_reports', r.get('reports',1) if r.get('source') in ('citizen','demo') else 0)
          r['reports']=r.get('reports',1)+1
          r.setdefault('sources', [r.get('source','unknown')])
          if data.get('source') not in r['sources']: r['sources'].append(data.get('source','unknown'))
          r['citizen_reports'] += 1 if data.get('source')=='citizen' else 0
          r['severity_score']=max(r.get('severity_score',0),data['severity_score'])
          event(r, 'Nearby '+data.get('source','new')+' observation grouped')
          save(items); return decorate(r), True
      data.update(id='RG-'+uuid.uuid4().hex[:6].upper(), timestamp=now(), status='Detected', reports=1, citizen_reports=1 if data.get('source')=='citizen' else 0, sources=[data.get('source','unknown')], team='', eta='')
      event(data, ('Simulated' if data.get('source')=='demo' else data.get('source','New').capitalize())+' observation created')
      items.insert(0,data); save(items); return decorate(data), False

def update(id, updates):
    with lock:
      items=get_raw()
      for r in items:
        if r['id']==id:
          changes=[]
          for key, value in updates.items():
            if r.get(key) != value:
              if key=='status': changes.append('Status changed to '+str(value))
              elif key in ('team','eta'): changes.append(key.capitalize()+' updated: '+(str(value) or 'not set'))
              else: changes.append(key.replace('_',' ').capitalize()+' updated to '+str(value))
          r.update(updates)
          if changes: event(r, '; '.join(changes))
          save(items); return decorate(r)
      return None

def reset_demo():
    with lock:
      items=[r for r in get_raw() if r.get('source')!='demo']
      save(items+seed())
      return len(items)
