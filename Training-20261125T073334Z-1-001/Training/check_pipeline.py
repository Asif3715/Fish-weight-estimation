import os, tempfile, sys
os.environ['AQUAPENSE_DATA']=tempfile.mkdtemp(prefix='aquapense-check-')
sys.path.insert(0,r'C:\Users\AFAN\Downloads\FYP\Data Pipeline\backend')
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    assert c.get('/api/health').status_code==200
    camera={'id':'test_camera','name':'Front view','host':'192.0.2.1','username':'admin','password':'test-only','enabled':True}
    assert c.put('/api/cameras',json=[camera]).status_code==200
    rows=c.get('/api/cameras').json()
    assert rows[0]['password']=='' and rows[0]['has_password']
    camera['password']='';camera['name']='Renamed view'
    assert c.put('/api/cameras',json=[camera]).status_code==200
    assert c.get('/api/cameras').json()[0]['has_password']
    assert c.put('/api/cameras',json=[camera,camera]).status_code==400
    camera['id']='../escape'
    assert c.put('/api/cameras',json=[camera]).status_code==422
    assert c.post('/api/recordings/events',json={'kind':'feed_added'}).status_code==409
    assert c.get('/api/recordings').json()['runs']==[]
    assert c.post('/api/drive/connect').status_code==400
    assert c.get('/').status_code==200
print('PASS: API health, camera save/rename/password retention, secret redaction, duplicate/path validation, event guard, missing OAuth handling, built dashboard serving. No live camera or Drive access performed.')
