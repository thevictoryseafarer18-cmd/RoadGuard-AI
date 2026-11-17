"""Small standard-library regression suite. Run: python -m unittest test_roadguard"""
import io
import tempfile
import unittest
from unittest.mock import patch
import cv2
import numpy as np
import app as web
import database as db
from priority import priority, band, road_segments

class RoadGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.PATH
        db.PATH = self.temp.name + '/reports.json'
        db.initialize()
        web.state.update(mode='demo',latitude=9.9252,longitude=78.1198,location_source='demo')
        web.app.testing = True
        self.client = web.app.test_client()

    def tearDown(self):
        db.PATH = self.old_path
        self.temp.cleanup()

    def report(self, **overrides):
        payload={'damage_type':'POTHOLE','latitude':9.80,'longitude':78.00,'location':'Test road','severity_score':70}
        payload.update(overrides)
        return self.client.post('/api/reports',json=payload)

    def test_scoring_weights_and_bands(self):
        score, components=priority({'severity_score':100,'traffic':100,'road_importance':100,'sensitive_location':100,'citizen_reports':10})
        self.assertEqual(score,95) # age defaults to zero
        self.assertEqual(components['citizen_reports'],100)
        self.assertEqual([band(n) for n in (0,39,40,59,60,79,80,100)],['LOW','LOW','MEDIUM','MEDIUM','HIGH','HIGH','CRITICAL','CRITICAL'])

    def test_creation_and_nearby_grouping(self):
        a=self.report().get_json(); b=self.report(latitude=9.8001,longitude=78.0001).get_json()
        self.assertFalse(a['grouped']); self.assertTrue(b['grouped'])
        self.assertEqual(a['report']['id'],b['report']['id'])
        self.assertEqual(b['report']['citizen_reports'],2)
        self.assertTrue(b['report']['history'])
        c=self.report(latitude=9.81).get_json(); self.assertFalse(c['grouped'])

    def test_demo_and_real_do_not_group(self):
        r=self.report(latitude=9.9305,longitude=78.1475).get_json()
        self.assertFalse(r['grouped']);self.assertEqual(r['report']['source'],'citizen')

    def test_camera_observations_do_not_count_as_citizen_reports(self):
        record={'damage_type':'POTHOLE','latitude':9.81,'longitude':78.0,'location':'camera','severity_score':40,'source':'camera'}
        a,_=db.add(dict(record));b,grouped=db.add(dict(record))
        self.assertTrue(grouped);self.assertEqual(b['reports'],2);self.assertEqual(b['citizen_reports'],0)

    def test_status_and_context_updates(self):
        rid=self.report().get_json()['report']['id']
        r=self.client.patch('/api/reports/'+rid,json={'status':'Assigned','team':'Unit 42','eta':'Tomorrow','traffic':90}).get_json()
        self.assertEqual(r['team'],'Unit 42');self.assertEqual(r['traffic'],90);self.assertIn('Assigned',r['history'][-1]['message'])
        r=self.client.patch('/api/reports/'+rid,json={'status':'In Progress'}).get_json()
        self.assertEqual(r['team'],'Unit 42');self.assertEqual(r['eta'],'Tomorrow')
        self.assertEqual(self.client.patch('/api/reports/'+rid,json={'traffic':101}).status_code,400)
        self.assertEqual(self.client.patch('/api/reports/'+rid,json={'status':'Fake'}).status_code,400)

    def test_reset_preserves_real_records(self):
        rid=self.report().get_json()['report']['id']; self.client.post('/api/demo-event',json={'high':True})
        r=self.client.post('/api/demo-reset').get_json()
        self.assertEqual(r['preserved'],1);self.assertIn(rid,[x['id'] for x in db.all_reports()]);self.assertEqual(len(db.all_reports()),8)

    def test_csv_export_and_spreadsheet_formula_escape(self):
        self.report(location='=HYPERLINK("https://example.com")')
        r=self.client.get('/api/export.csv');self.assertEqual(r.status_code,200)
        self.assertIn("'=HYPERLINK",r.get_data(as_text=True));self.assertIn('text/csv',r.content_type)

    def test_image_analysis_success_and_bad_file(self):
        image=np.zeros((100,100,3),dtype=np.uint8);ok,encoded=cv2.imencode('.jpg',image);self.assertTrue(ok)
        with patch.object(web.detector,'detect',return_value=[(10,55,80,90,'POTHOLE',70,60)]):
            r=self.client.post('/api/analyze',data={'image':(io.BytesIO(encoded.tobytes()),'road.jpg')},content_type='multipart/form-data')
        self.assertEqual(r.status_code,200);j=r.get_json();self.assertEqual(j['detections'][0]['severity'],'HIGH');self.assertTrue(j['image'].startswith('data:image/jpeg;base64,'))
        bad=self.client.post('/api/analyze',data={'image':(io.BytesIO(b'bad'),'bad.jpg')},content_type='multipart/form-data');self.assertEqual(bad.status_code,400)

    def test_camera_falls_back_safely(self):
        with patch.object(web.cv2,'VideoCapture') as capture:
            capture.return_value.isOpened.return_value=False
            result=self.client.post('/api/mode',json={'mode':'live'}).get_json()
        self.assertEqual(result['mode'],'demo');self.assertIn('unavailable',result['camera_note'])

    def test_per_segment_health(self):
        segments=road_segments(db.all_reports())
        self.assertTrue(segments); self.assertTrue(all(0<=s['health']<=100 for s in segments))
        self.assertEqual(next(s for s in segments if s['location']=='East Veli Street')['health'],100)

if __name__ == '__main__': unittest.main()
