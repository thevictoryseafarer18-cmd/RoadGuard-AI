import os, time, random, threading, csv, io, base64
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, render_template, request, Response
import cv2
import numpy as np
import database as db
from priority import deterioration, band, road_segments
from detector import Detector

app=Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 6 * 1024 * 1024
db.initialize()
detector=Detector()
state={'mode':'demo','latitude':9.9252,'longitude':78.1198,'location_source':'demo','camera_note':'Demo mode active'}
state_lock=threading.Lock()
camera=None
camera_lock=threading.Lock()
last_live_record=0

@app.get('/')
def index(): return render_template('index.html')

@app.get('/api/state')
def api_state():
    reports=db.all_reports(); active=[r for r in reports if r['status']!='Repaired']
    with state_lock: current=dict(state)
    weekly=[]
    for days in range(6,-1,-1):
      date=(datetime.now(timezone.utc)-timedelta(days=days)).date()
      weekly.append({'label':date.strftime('%a'),'count':sum(1 for r in reports if r.get('timestamp','')[:10]==date.isoformat())})
    return jsonify(reports=reports, stats={'detections':len(reports),'critical':sum(r['priority']>=80 for r in active),'citizen_reports':sum(r.get('citizen_reports',0) for r in reports),'repaired':sum(r['status']=='Repaired' for r in reports)}, risk=deterioration(reports), segments=road_segments(reports), weekly=weekly, state=current, detector=detector.model_note)

@app.post('/api/mode')
def set_mode():
    global camera
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict): return jsonify(error='Expected a JSON object'),400
    mode=payload.get('mode')
    if mode not in ('demo','live'): return jsonify(error='Invalid mode'),400
    if mode=='live':
      with camera_lock:
        try:
          if camera is None or not camera.isOpened(): camera=cv2.VideoCapture(0)
          ok=bool(camera.isOpened())
          if ok: ok,_=camera.read()
        except (cv2.error, OSError): ok=False
        if not ok:
          if camera: camera.release()
          camera=None
      with state_lock:
        state['mode']='live' if ok else 'demo'; state['camera_note']='Camera connected' if ok else 'Camera unavailable — demo mode enabled'
    else:
      with camera_lock:
        if camera: camera.release()
        camera=None
      with state_lock: state['mode']='demo'; state['camera_note']='Demo mode active'
    return jsonify(state)

@app.post('/api/location')
def location():
    d=request.get_json(silent=True)
    if not isinstance(d,dict): return jsonify(error='Expected a JSON object'),400
    try:
      lat=float(d['latitude']); lng=float(d['longitude'])
      if not (-90<=lat<=90 and -180<=lng<=180): raise ValueError()
    except (KeyError,ValueError,TypeError): return jsonify(error='Invalid coordinates'),400
    with state_lock: state.update(latitude=lat,longitude=lng,location_source='browser')
    return jsonify(state)

@app.post('/api/reports')
def add_report():
    d=request.get_json(silent=True)
    if not isinstance(d,dict): return jsonify(error='Expected a JSON object'),400
    try:
      typ=str(d.get('damage_type','POTHOLE')).upper()
      if typ not in db.TYPES: raise ValueError('Invalid damage type')
      lat=float(d.get('latitude',state['latitude'])); lng=float(d.get('longitude',state['longitude']))
      if not (-90<=lat<=90 and -180<=lng<=180): raise ValueError('Invalid coordinates')
      sev=max(0,min(100,int(d.get('severity_score',50))))
      data={'damage_type':typ,'latitude':lat,'longitude':lng,'location':str(d.get('location','Current location'))[:120].strip() or 'Current location','severity_score':sev,'description':str(d.get('description',''))[:500],'confidence':None,'source':'citizen','traffic':50,'road_importance':50,'sensitive_location':0}
      r,grouped=db.add(data); return jsonify(report=r,grouped=grouped),201
    except (ValueError,TypeError) as e: return jsonify(error=str(e)),400

@app.patch('/api/reports/<id>')
def update_report(id):
    d=request.get_json(silent=True)
    if not isinstance(d,dict): return jsonify(error='Expected a JSON object'),400
    updates={}
    if 'status' in d:
      if d['status'] not in db.STATUSES: return jsonify(error='Invalid status'),400
      updates['status']=d['status']
      if d['status'] in ('Assigned','In Progress'):
        current=next((r for r in db.all_reports() if r['id']==id),None)
        if current:
          updates['team']=str(d.get('team') or current.get('team') or 'Road Maintenance Unit 04')[:100]
          updates['eta']=str(d.get('eta') or current.get('eta') or '2 days')[:50]
    for key in ('team','eta'):
      if key in d: updates[key]=str(d[key]).strip()[:100]
    try:
      for key in ('severity_score','traffic','road_importance','sensitive_location'):
        if key in d:
          value=int(d[key])
          if not 0 <= value <= 100: raise ValueError(key+' must be between 0 and 100')
          updates[key]=value
    except (ValueError,TypeError) as e: return jsonify(error=str(e) or 'Invalid score'),400
    result=db.update(id,updates)
    return (jsonify(result) if result else (jsonify(error='Not found'),404))

@app.get('/api/export.csv')
def export_csv():
    fields=['id','timestamp','location','latitude','longitude','damage_type','source','sources','confidence','severity_score','severity','priority','priority_band','status','reports','citizen_reports','team','eta','description']
    output=io.StringIO(newline='')
    writer=csv.DictWriter(output,fieldnames=fields,extrasaction='ignore')
    writer.writeheader()
    for row in db.all_reports():
      # Prevent user-provided strings from being interpreted as spreadsheet formulas.
      safe={k: ("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v) for k,v in row.items()}
      writer.writerow(safe)
    return Response(output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=roadguard-reports.csv'})

@app.post('/api/demo-reset')
def demo_reset():
    if state['mode']!='demo': return jsonify(error='Switch to demo mode before resetting'),400
    preserved=db.reset_demo()
    return jsonify(message='Demo data reset', preserved=preserved)

@app.post('/api/analyze')
def analyze_image():
    file=request.files.get('image')
    if not file or not file.filename: return jsonify(error='Choose a JPG, PNG or WebP image'),400
    raw=file.read(5 * 1024 * 1024 + 1)
    if len(raw)>5*1024*1024: return jsonify(error='Image must be under 5 MB'),413
    frame=cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
    if frame is None: return jsonify(error='This image could not be decoded'),400
    h,w=frame.shape[:2]
    if h < 32 or w < 32: return jsonify(error='Image is too small'),400
    scale=min(1,960/max(h,w)); frame=cv2.resize(frame,(max(1,int(w*scale)),max(1,int(h*scale))))
    found=detector.detect(frame); results=[]
    for x1,y1,x2,y2,name,confidence,severity in found:
      color=(75,100,255) if severity>=60 else (30,190,245)
      cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)
      cv2.rectangle(frame,(x1,max(0,y1-24)),(min(frame.shape[1]-1,x1+250),y1),color,-1)
      cv2.putText(frame,f'{name} ~{confidence}% {band(severity)}',(x1+4,max(14,y1-6)),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1,cv2.LINE_AA)
      results.append({'damage_type':name,'confidence':confidence,'severity_score':severity,'severity':band(severity)})
    ok,encoded=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,78])
    if not ok: return jsonify(error='Could not prepare result image'),500
    return jsonify(image='data:image/jpeg;base64,'+base64.b64encode(encoded).decode('ascii'),detections=results,method=detector.model_note,notice='Unverified image candidates. Heuristic confidence is not a calibrated probability. Image is not stored.')

@app.errorhandler(413)
def too_large(e): return jsonify(error='File is too large; choose an image under 5 MB'),413

@app.post('/api/demo-event')
def demo_event():
    if state['mode']!='demo': return jsonify(error='Only available in demo mode'),400
    candidates=[('Anna Nagar Main Road',9.9305,78.1475),('K.K. Nagar Junction',9.9360,78.1506),('Goripalayam Road',9.9325,78.1309),('Alagarkoil Main Road',9.9446,78.1585),('Lake View Road',9.9206,78.1501)]
    name,lat,lng=random.choice(candidates); typ=random.choice(db.TYPES); d=request.get_json(silent=True) or {}; sev=random.randint(80,96) if isinstance(d,dict) and d.get('high') is True else random.randint(42,96)
    data={'damage_type':typ,'latitude':lat+random.uniform(-.0003,.0003),'longitude':lng+random.uniform(-.0003,.0003),'location':name,'severity_score':sev,'description':'Simulated detection; not a real observation.','confidence':random.randint(75,98),'source':'demo','traffic':random.randint(55,95),'road_importance':random.randint(50,95),'sensitive_location':random.choice([0,40,80,100])}
    r,grouped=db.add(data); return jsonify(report=r,grouped=grouped)

def frames():
    global last_live_record
    previous=time.time()
    while state['mode']=='live':
      with camera_lock:
        if camera is None: break
        ok,frame=camera.read()
      if not ok:
        with state_lock: state.update(mode='demo',camera_note='Camera disconnected — demo mode enabled')
        break
      frame=cv2.resize(frame,(640,360)); detections=detector.detect(frame)
      fps=min(99,1/max(.001,time.time()-previous)); previous=time.time()
      for x1,y1,x2,y2,name,confidence,severity in detections:
        color=(75,100,255) if severity>=60 else (30,190,245)
        cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)
        cv2.rectangle(frame,(x1,max(0,y1-25)),(min(639,x1+250),y1),color,-1)
        cv2.putText(frame,f'{name} ~{confidence}% {band(severity)}',(x1+4,max(15,y1-7)),cv2.FONT_HERSHEY_SIMPLEX,.43,(255,255,255),1,cv2.LINE_AA)
      cv2.putText(frame,f'FPS {fps:.0f}  |  CANDIDATES {len(detections)}',(12,345),cv2.FONT_HERSHEY_SIMPLEX,.48,(255,255,255),1,cv2.LINE_AA)
      if detections and time.time()-last_live_record>20:
        last_live_record=time.time(); x1,y1,x2,y2,name,confidence,severity=detections[0]
        with state_lock: lat,lng=state['latitude'],state['longitude']; loc_source=state['location_source']
        db.add({'damage_type':name,'latitude':lat,'longitude':lng,'location':'Camera location' if loc_source=='browser' else 'Demo coordinates (GPS unavailable)','severity_score':severity,'description':'Unverified camera candidate; inspect before acting.','confidence':confidence,'source':'camera','traffic':50,'road_importance':50,'sensitive_location':0})
      ok,encoded=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,75])
      if ok: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'+encoded.tobytes()+b'\r\n')
      time.sleep(.02)

@app.get('/video_feed')
def video_feed(): return Response(frames(),mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),threaded=True)
