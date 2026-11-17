"""A lightweight heuristic detector; estimates are not model probabilities."""
import cv2, numpy as np, time, os
from priority import severity_estimate

class Detector:
    def __init__(self):
        self.model = None
        self.model_note = 'OpenCV heuristic'
        path = os.environ.get('ROADGUARD_MODEL', '')
        if path and os.path.isfile(path):
            try:
                from ultralytics import YOLO  # optional, installed separately; never downloads a model
                self.model = YOLO(path); self.model_note = 'Local YOLO model'
            except Exception as e: self.model_note = 'OpenCV heuristic (local model unavailable)'

    def detect(self, frame):
        h,w=frame.shape[:2]
        if self.model:
            try:
                results=self.model.predict(frame, verbose=False, imgsz=416, conf=.35)
                found=[]
                for b in results[0].boxes:
                    name=str(results[0].names[int(b.cls[0])]).upper().replace('_',' ')
                    if name not in ('POTHOLE','CRACK','ROAD DAMAGE','OPEN MANHOLE','ROAD EDGE DAMAGE'): continue
                    x1,y1,x2,y2=map(int,b.xyxy[0].tolist()); conf=float(b.conf[0]); size=(x2-x1)*(y2-y1)/(w*h)
                    found.append((x1,y1,x2,y2,name,round(conf*100),severity_estimate(size)))
                return found[:5]
            except Exception: pass
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        gray=cv2.GaussianBlur(gray,(7,7),0)
        # Only examine road-like lower half; dark regions are candidates, not confirmed potholes.
        cutoff=max(28, min(90, int(np.percentile(gray[int(h*.45):],20))))
        mask=cv2.threshold(gray,cutoff,255,cv2.THRESH_BINARY_INV)[1]
        mask[:int(h*.48),:]=0
        kernel=np.ones((7,7),np.uint8)
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,kernel,iterations=2)
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        found=[]
        for c in sorted(contours,key=cv2.contourArea,reverse=True)[:5]:
            x,y,bw,bh=cv2.boundingRect(c); area=cv2.contourArea(c); ratio=area/(w*h)
            if .008 < ratio < .18 and bw>35 and bh>15 and .25<bw/max(bh,1)<5:
                # Relative image size heuristic, not physical dimensions or calibrated confidence.
                severity=severity_estimate(ratio); confidence=min(85,round(45+ratio*300))
                found.append((x,y,x+bw,y+bh,'POTHOLE',confidence,severity))
        return found
