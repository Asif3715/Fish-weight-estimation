import os,tempfile,sys
sys.path.insert(0,r'C:\Users\AFAN\Downloads\FYP\Data Pipeline\backend')
os.environ['AQUAPENSE_DATA']=tempfile.mkdtemp(prefix='aquapense-preview-check-')
from fastapi.testclient import TestClient
from fastapi import HTTPException
from unittest.mock import patch
from app.main import app
class GoodPreview:
 def __init__(self,camera): pass
 def close(self): pass
 async def stream(self,request):
  yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n\xff\xd8\xff\xd9\r\n'
cam={'id':'test','name':'Test view','host':'10.0.0.2','username':'admin','password':'test-only','stream':'/Streaming/Channels/101','enabled':True}
with TestClient(app) as client:
 assert client.get('/api/cameras/missing/preview').status_code==404
 with patch('app.modules.cameras.preview.Preview',side_effect=HTTPException(502,'Camera rejected credentials')):
  assert client.post('/api/cameras/connect',json=cam).status_code==502
  assert client.get('/api/cameras').json()==[]
 with patch('app.modules.cameras.preview.Preview',GoodPreview):
  assert client.post('/api/cameras/connect',json=cam).json()['verified']
  saved=client.get('/api/cameras').json()[0]
  assert saved['password']=='' and saved['has_password']
  response=client.get('/api/cameras/test/preview')
  assert response.status_code==200 and b'\xff\xd8' in response.content
 print('PASS: failed authentication preserves settings; verified save; password redaction; multipart preview; missing camera.')
