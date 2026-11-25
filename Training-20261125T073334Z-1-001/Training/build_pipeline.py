from pathlib import Path
import json

ROOT = Path(r'C:\Users\AFAN\Downloads\FYP\Data Pipeline')
files = {}
def add(path, content): files[path] = content.lstrip('\n')

add('backend/requirements.txt', '''
fastapi>=0.115,<1
uvicorn>=0.30,<1
google-api-python-client>=2,<3
google-auth-oauthlib>=1,<2
''')
add('.gitignore', '''
runtime/
**/.venv/
**/__pycache__/
**/node_modules/
frontend/dist/
.env
credentials.json
token.json
''')
add('backend/app/core/config.py', '''
from pathlib import Path
import os
ROOT = Path(__file__).resolve().parents[3]
DATA = Path(os.environ.get('AQUAPENSE_DATA', str(ROOT / 'runtime')))
DATA.mkdir(parents=True, exist_ok=True)
FFMPEG = os.environ.get('FFMPEG_PATH', 'ffmpeg')
''')
add('backend/app/db/database.py', '''
import sqlite3, json, threading
from app.core.config import DATA
lock = threading.RLock()
def connect():
    c = sqlite3.connect(DATA / 'catalogue.sqlite', timeout=30)
    c.row_factory = sqlite3.Row
    return c
def init():
    with connect() as c:
        c.executescript(''' + '"""' + '''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, mode TEXT, start TEXT, end TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, run_id TEXT, utc TEXT, kind TEXT, note TEXT);
        CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, run_id TEXT, camera TEXT, state TEXT DEFAULT 'pending', drive_id TEXT, error TEXT);
        ''' + '"""' + ''')
        c.execute("UPDATE files SET state='pending' WHERE state='uploading'")
        c.execute("UPDATE runs SET end='interrupted: server restarted' WHERE end IS NULL")
def get(key, default=None):
    with connect() as c:
        row = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default
def put(key, value):
    with connect() as c:
        c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))
''')
add('backend/app/modules/cameras/router.py', '''
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.db.database import get, put
router = APIRouter(prefix='/cameras')
class Camera(BaseModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]+$')
    name: str
    host: str
    username: str = 'admin'
    password: str = ''
    stream: str = '/Streaming/Channels/101'
    enabled: bool = True
@router.get('')
def list_cameras():
    return [{**c, 'password': '', 'has_password': bool(c.get('password'))} for c in get('cameras', [])]
@router.put('')
def save(cameras: list[Camera]):
    from app.modules.recordings.service import recorder
    if recorder.active: raise HTTPException(409, 'Stop recording before changing cameras')
    if len({c.id for c in cameras}) != len(cameras): raise HTTPException(400, 'Camera IDs must be unique')
    old = {c['id']: c for c in get('cameras', [])}
    rows = [c.model_dump() for c in cameras]
    for c in rows:
        if not c['password']: c['password'] = old.get(c['id'], {}).get('password', '')
        if not c['stream'].startswith('/'): raise HTTPException(400, 'Stream path must start with /')
    put('cameras', rows)
    return {'saved': True}
''')
add('backend/app/modules/recordings/service.py', '''
import subprocess, threading, time, uuid, json, shutil
from datetime import datetime, timezone
from urllib.parse import quote
from app.core.config import DATA, FFMPEG
from app.db.database import connect, get
def utc(): return datetime.now(timezone.utc).isoformat()
class Recorder:
    def __init__(self):
        self.active = None
        self.stopping = threading.Event()
        self.threads = []
        self.processes = {}
        self.status = {}
        self.lock = threading.RLock()
    def event(self, kind, note=''):
        with connect() as c:
            c.execute('INSERT INTO events(run_id,utc,kind,note) VALUES (?,?,?,?)', (self.active, utc(), kind, note))
    def start(self, mode):
        with self.lock:
            if self.active: raise ValueError('Already recording')
            cameras = [c for c in get('cameras', []) if c['enabled']]
            if not cameras: raise ValueError('Configure and enable at least one camera')
            if not shutil.which(FFMPEG): raise ValueError('FFmpeg is not installed or FFMPEG_PATH is invalid')
            if shutil.disk_usage(DATA).free < 2 * 1024**3: raise ValueError('At least 2 GB free space required')
            self.active = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:8]
            self.stopping.clear()
            self.status = {}
            with connect() as c: c.execute('INSERT INTO runs VALUES (?,?,?,NULL)', (self.active, mode, utc()))
            folder = DATA / 'recordings' / self.active
            folder.mkdir(parents=True)
            manifest = {'id': self.active, 'mode': mode, 'start_utc': utc(), 'cameras': [{'id':c['id'], 'name':c['name']} for c in cameras], 'timing_alignment':'unverified', 'sensors':'not connected', 'target_minimum_fps':5}
            (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2))
            self.threads = [threading.Thread(target=self.worker, args=(camera, folder, self.active), daemon=True) for camera in cameras]
            for t in self.threads: t.start()
            return self.active
    def register(self, paths, run, camera):
        with connect() as c:
            for p in paths:
                if p.exists() and p.stat().st_size:
                    c.execute('INSERT OR IGNORE INTO files(path,run_id,camera) VALUES (?,?,?)', (str(p.relative_to(DATA)), run, camera))
    def worker(self, camera, folder, run):
        cid = camera['id']
        attempt = 0
        while not self.stopping.is_set():
            if shutil.disk_usage(DATA).free < 1024**3:
                self.status[cid] = 'Paused: low disk space'
                self.stopping.wait(5)
                continue
            attempt += 1
            dest = folder / cid / str(attempt)
            dest.mkdir(parents=True)
            url = 'rtsp://' + quote(camera['username'], safe='') + ':' + quote(camera['password'], safe='') + '@' + camera['host'] + ':554' + camera['stream']
            command = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-rtsp_transport', 'tcp', '-rw_timeout', '15000000', '-i', url, '-map', '0:v:0', '-an', '-c:v', 'copy', '-f', 'segment', '-segment_time', '60', '-reset_timestamps', '0', '-segment_list', str(dest / 'segments.csv'), '-segment_list_type', 'csv', str(dest / '%06d.mkv')]
            try:
                p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.processes[cid] = p
                self.status[cid] = 'Connecting / recording — FPS not verified'
                self.event('camera_attempt', cid + ': ' + str(attempt))
                while p.poll() is None and not self.stopping.wait(1):
                    chunks = sorted(dest.glob('*.mkv'))
                    self.register(chunks[:-1], run, cid)
                if p.poll() is None:
                    try:
                        p.communicate(b'q', timeout=10)
                    except subprocess.TimeoutExpired:
                        p.kill(); p.wait()
                # Only chunks listed by the segment muxer are known closed.
                import csv
                listing = dest / 'segments.csv'
                if listing.exists():
                    with listing.open(newline='') as f:
                        self.register([dest / Path(row[0]).name for row in csv.reader(f) if row], run, cid)
                self.status[cid] = 'Disconnected; reconnecting' if not self.stopping.is_set() else 'Stopped'
                self.event('camera_exit', cid + ': exit ' + str(p.returncode))
            except Exception as e:
                self.status[cid] = 'Camera worker error: ' + type(e).__name__
            if not self.stopping.is_set(): self.stopping.wait(3)
    def stop(self):
        with self.lock:
            if not self.active: return
            self.stopping.set()
            for t in self.threads: t.join(30)
            folder = DATA / 'recordings' / self.active
            with connect() as c:
                rows = [dict(r) for r in c.execute('SELECT * FROM events WHERE run_id=?', (self.active,))]
                c.execute('UPDATE runs SET end=? WHERE id=?', (utc(), self.active))
            (folder / 'events.json').write_text(json.dumps(rows, indent=2))
            self.register([folder / 'events.json', folder / 'manifest.json', *folder.glob('*/ */segments.csv')], self.active, '')
            self.active = None
from pathlib import Path
recorder = Recorder()
''')
add('backend/app/modules/recordings/router.py', '''
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal
from app.modules.recordings.service import recorder
from app.db.database import connect
router = APIRouter(prefix='/recordings')
class Start(BaseModel): mode: Literal['session', 'continuous'] = 'session'
class Event(BaseModel):
    kind: Literal['experiment_start','feed_added','observation','disturbance','experiment_end','timing_marker']
    note: str = ''
@router.get('')
def listing():
    with connect() as c:
        return {'active': recorder.active, 'cameras':recorder.status, 'runs':[dict(r) for r in c.execute('SELECT * FROM runs ORDER BY start DESC')], 'files':[dict(r) for r in c.execute('SELECT * FROM files ORDER BY rowid DESC LIMIT 500')]}
@router.post('/start')
def start(body: Start):
    try: return {'id':recorder.start(body.mode)}
    except ValueError as e: raise HTTPException(400, str(e))
@router.post('/stop')
def stop():
    recorder.stop()
    return {'stopped':True}
@router.post('/events')
def event(body: Event):
    if not recorder.active: raise HTTPException(409, 'Start recording first')
    recorder.event(body.kind, body.note)
    return {'saved':True}
''')
add('backend/app/modules/drive/router.py', '''
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db.database import get, put, connect
from app.core.config import DATA
from app.modules.drive.service import authenticate, upload_pending
router = APIRouter(prefix='/drive')
class Settings(BaseModel): folder_id: str
@router.get('')
def status(): return {'configured':(DATA/'secrets/credentials.json').exists(), 'connected':(DATA/'secrets/token.json').exists(), 'folder_id':get('drive_folder',''), 'auth_status':get('drive_auth_status','Not connected')}
@router.put('')
def settings(body:Settings):
    put('drive_folder', body.folder_id.strip())
    return {'saved':True}
@router.post('/connect')
def auth(): return authenticate()
@router.post('/upload')
def upload():
    if not get('drive_folder'): raise HTTPException(400, 'Set a destination folder ID')
    return upload_pending()
''')
add('backend/app/modules/drive/service.py', '''
import threading, mimetypes
from app.core.config import DATA
from app.db.database import get, put, connect
from fastapi import HTTPException
SCOPES = ['https://www.googleapis.com/auth/drive.file']
SECRETS = DATA / 'secrets'
lock = threading.Lock()
auth_lock = threading.Lock()
def authenticate():
    if not (SECRETS/'credentials.json').exists(): raise HTTPException(400, 'Place Desktop OAuth credentials.json in runtime/secrets first')
    if not auth_lock.acquire(False): return {'status':'Sign-in already running'}
    def work():
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            put('drive_auth_status','Waiting for sign-in on edge PC browser')
            flow = InstalledAppFlow.from_client_secrets_file(str(SECRETS/'credentials.json'), SCOPES)
            creds = flow.run_local_server(host='localhost', port=8765, timeout_seconds=180)
            (SECRETS/'token.json').write_text(creds.to_json())
            put('drive_auth_status','Connected')
        except Exception as e: put('drive_auth_status','Sign-in failed: '+type(e).__name__)
        finally: auth_lock.release()
    threading.Thread(target=work, daemon=True).start()
    return {'status':'Complete sign-in in the edge PC browser'}
def upload_pending():
    if not lock.acquire(False): return {'status':'Upload already running'}
    def work():
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            creds = Credentials.from_authorized_user_file(str(SECRETS/'token.json'), SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request()); (SECRETS/'token.json').write_text(creds.to_json())
            service = build('drive','v3',credentials=creds)
            while True:
                with connect() as c:
                    row = c.execute("SELECT * FROM files WHERE state='pending' LIMIT 1").fetchone()
                    if not row: break
                    row = dict(row)
                    c.execute("UPDATE files SET state='uploading' WHERE path=?", (row['path'],))
                try:
                    # Allocate and persist an ID before upload, making retries idempotent.
                    fid = row['drive_id']
                    if not fid:
                        fid = service.files().generateIds(count=1).execute()['ids'][0]
                        with connect() as c: c.execute('UPDATE files SET drive_id=? WHERE path=?',(fid,row['path']))
                    try:
                        service.files().get(fileId=fid,fields='id').execute()
                    except Exception as ex:
                        if getattr(getattr(ex,'resp',None),'status',None) != 404: raise
                        media = MediaFileUpload(str(DATA/row['path']), resumable=True, mimetype=mimetypes.guess_type(row['path'])[0] or 'application/octet-stream')
                        service.files().create(body={'id':fid,'name':row['path'].replace('\\\\','__').replace('/','__'),'parents':[get('drive_folder')]},media_body=media,fields='id').execute()
                    with connect() as c: c.execute("UPDATE files SET state='uploaded',error=NULL WHERE path=?",(row['path'],))
                except Exception as e:
                    with connect() as c: c.execute("UPDATE files SET state='pending',error=? WHERE path=?",(type(e).__name__,row['path']))
                    break
        except Exception as e: put('drive_auth_status','Upload unavailable: '+type(e).__name__)
        finally: lock.release()
    threading.Thread(target=work,daemon=True).start()
    return {'status':'Upload queue started; click again to retry after failure'}
''')
add('backend/app/main.py', '''
from contextlib import asynccontextmanager
import shutil
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import init
from app.core.config import DATA, FFMPEG
from app.modules.cameras.router import router as cameras
from app.modules.recordings.router import router as recordings
from app.modules.drive.router import router as drive
from app.modules.recordings.service import recorder
@asynccontextmanager
async def lifespan(app):
    init()
    yield
    recorder.stop()
app = FastAPI(title='AquaPense Collection', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173','http://127.0.0.1:5173'], allow_methods=['*'], allow_headers=['*'])
for router in (cameras, recordings, drive): app.include_router(router,prefix='/api')
@app.get('/api/health')
def health(): return {'ffmpeg_available':bool(shutil.which(FFMPEG)), 'free_gb':round(shutil.disk_usage(DATA).free/1024**3,1),'sensors':'Not connected','timing':'Unverified','fps':'Not measured'}
''')
add('frontend/package.json', json.dumps({'name':'aquapense-collection','private':True,'version':'0.1.0','type':'module','scripts':{'dev':'vite --host 127.0.0.1','build':'tsc && vite build'},'dependencies':{'react':'^19.0.0','react-dom':'^19.0.0'},'devDependencies':{'typescript':'^5.7.0','vite':'^6.0.0','@types/react':'^19.0.0','@types/react-dom':'^19.0.0'}},indent=2))
add('frontend/tsconfig.json', json.dumps({'compilerOptions':{'target':'ES2022','lib':['ES2022','DOM'],'module':'ESNext','moduleResolution':'Bundler','jsx':'react-jsx','strict':True,'noEmit':True,'skipLibCheck':True},'include':['src']}))
add('frontend/vite.config.ts', "import {defineConfig} from 'vite';\nexport default defineConfig({server:{proxy:{'/api':'http://127.0.0.1:8000'}}});\n")
add('frontend/index.html', '<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>AquaPense Collection</title></head><body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>')
add('frontend/src/main.tsx', '''
import React, {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './styles.css';
async function api(path:string, method='GET', body?:unknown){ const r=await fetch('/api/'+path,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)}); const data=await r.json(); if(!r.ok)throw Error(data.detail||'Request failed');return data; }
type Camera={id:string;name:string;host:string;username:string;password:string;stream:string;enabled:boolean};
function App(){
 const [tab,T]=useState('Overview'),[health,H]=useState<any>({}),[record,R]=useState<any>({runs:[],files:[],cameras:{}}),[drive,D]=useState<any>({}),[cameras,C]=useState<Camera[]>([]),[message,M]=useState(''),[mode,S]=useState('session'),[note,N]=useState(''),[folder,F]=useState('');
 async function refresh(){const [h,r,d]=await Promise.all([api('health'),api('recordings'),api('drive')]);H(h);R(r);D(d);}
 useEffect(()=>{api('cameras').then(C).catch(e=>M(e.message));api('drive').then(d=>F(d.folder_id));refresh().catch(e=>M(e.message));const t=setInterval(()=>refresh().catch(e=>M(e.message)),3000);return()=>clearInterval(t);},[]);
 async function action(fn:()=>Promise<any>){try{const r=await fn();M(r.status||'Saved');await refresh();}catch(e){M((e as Error).message);}}
 return <div className="shell"><aside><h2>◉ AquaPense</h2><p>DATA COLLECTION</p>{['Overview','Devices','Experiments','Recordings','Storage & Drive'].map(x=><button className={tab===x?'selected':''} key={x} onClick={()=>T(x)}>{x}</button>)}<small>Local edge recorder<br/>Sensors added later</small></aside><main><header><div><p>AQUARIUM RESEARCH</p><h1>{tab}</h1></div><span className="badge">{record.active?'● Recording':'○ Idle'}</span></header>{message&&<div role="status" className="notice">{message}<button onClick={()=>M('')}>Dismiss</button></div>}
 {tab==='Overview'&&<><div className="stats"><article><label>LOCAL SPACE</label><h2>{health.free_gb??'—'} GB</h2></article><article><label>SENSORS</label><h2>Not connected</h2></article><article><label>TIME ALIGNMENT</label><h2>Unverified</h2></article></div><section><h2>Collection controls</h2><select value={mode} onChange={e=>S(e.target.value)}><option value="session">Standalone session</option><option value="continuous">Continuous recording</option></select><button disabled={!!record.active} onClick={()=>action(()=>api('recordings/start','POST',{mode}))}>Start recording</button><button disabled={!record.active} onClick={()=>action(()=>api('recordings/stop','POST'))}>Stop recording</button><p>60-second compressed video chunks · original camera frame rate · no automatic deletion</p>{!health.ffmpeg_available&&<p className="warning">FFmpeg is required before recording can start.</p>}</section><div className="stats">{cameras.map(c=><article key={c.id}><h2>{c.name}</h2><div className="placeholder">Live preview pending</div><p>{record.cameras[c.id]||'Idle'}</p><small>Minimum target: 5 FPS · actual FPS not verified</small></article>)}</div></>}
 {tab==='Devices'&&<section><h2>Camera connections</h2><p>Use the same RTSP path as your reference script. Passwords stay on the edge PC.</p>{cameras.map((c,i)=><article key={i}><h3>Camera {i+1}</h3>{(['id','name','host','username','password','stream'] as const).map(k=><label className="field" key={k}>{k}<input type={k==='password'?'password':'text'} value={c[k]} placeholder={k==='password'?'Leave blank to keep saved password':''} onChange={e=>C(cameras.map((x,j)=>j===i?{...x,[k]:e.target.value}:x))}/></label>)}<label><input type="checkbox" checked={c.enabled} onChange={e=>C(cameras.map((x,j)=>j===i?{...x,enabled:e.target.checked}:x))}/> Enabled</label></article>)}<button onClick={()=>C([...cameras,{id:'camera_'+(cameras.length+1),name:cameras.length?'Top view':'Front view',host:'',username:'admin',password:'',stream:'/Streaming/Channels/101',enabled:true}])}>Add camera</button><button onClick={()=>action(()=>api('cameras','PUT',cameras))}>Save devices</button></section>}
 {tab==='Experiments'&&<section><h2>Feeding event markers</h2><p>Start recording first. Mark an experiment within continuous collection or a standalone session.</p><textarea placeholder="Amount, observation or experiment name" value={note} onChange={e=>N(e.target.value)}/><div>{[['experiment_start','Start experiment'],['feed_added','Mark feed added'],['observation','Add observation'],['disturbance','Mark disturbance'],['timing_marker','Mark timing event'],['experiment_end','End experiment']].map(([kind,title])=><button disabled={!record.active} key={kind} onClick={()=>action(()=>api('recordings/events','POST',{kind,note}))}>{title}</button>)}</div><p>A timing event alone does not verify camera alignment. A visible shared marker is needed.</p></section>}
 {tab==='Recordings'&&<><section><h2>Collection runs</h2><div className="table"><table><thead><tr><th>ID</th><th>Mode</th><th>Started UTC</th><th>Ended</th></tr></thead><tbody>{record.runs.map((r:any)=><tr key={r.id}><td>{r.id}</td><td>{r.mode}</td><td>{r.start}</td><td>{r.end||'Active'}</td></tr>)}</tbody></table></div></section><section><h2>File catalogue</h2>{record.files.length===0?<p>No completed files yet.</p>:record.files.map((f:any)=><p key={f.path}><code>{f.path}</code> · {f.state} {f.error&&'· '+f.error}</p>)}</section></>}
 {tab==='Storage & Drive'&&<section><h2>Google Drive</h2><p>{drive.auth_status}</p><p>Initial local setup: sign in using the browser on the edge PC. VPN sign-in will need a separate web OAuth configuration.</p><button onClick={()=>action(()=>api('drive/connect','POST'))}>Connect Google Drive</button><label className="field">Destination folder ID<input value={folder} onChange={e=>F(e.target.value)}/></label><p>Use a folder created by this app; arbitrary existing folders may not be accessible with the limited Drive permission.</p><button onClick={()=>action(()=>api('drive','PUT',{folder_id:folder}))}>Save destination</button><button onClick={()=>action(()=>api('drive/upload','POST'))}>Upload pending / retry</button><p>Local files are retained. Internet or Drive sign-in failures do not stop recording.</p></section>}
 </main></div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
''')
add('frontend/src/styles.css', '''
*{box-sizing:border-box}body{margin:0;font-family:Inter,Segoe UI,sans-serif;background:#f2f6f5;color:#193630}.shell{display:flex;min-height:100vh}aside{width:235px;background:#102f2a;color:#eef7f3;padding:28px;position:fixed;height:100vh}aside p{font-size:10px;letter-spacing:2px;color:#8fbbb0}aside button{display:block;width:100%;text-align:left;background:none;color:#bad2ca;border:0;margin:8px 0}aside .selected{background:#285348;color:white}aside small{position:absolute;bottom:30px;color:#8fbbb0;line-height:1.8}main{margin-left:235px;padding:35px 45px;width:calc(100% - 235px);max-width:1600px}header{display:flex;align-items:center;justify-content:space-between;margin-bottom:25px}header p{font-size:11px;letter-spacing:2px;color:#58786e}h1{font-size:32px;margin:8px 0}h2{font-size:20px}button,select,input,textarea{font:inherit;border-radius:8px;border:1px solid #cddbd5;padding:11px}button{cursor:pointer;background:#e4eee8;color:#173d32;margin:5px}button:disabled{opacity:.45;cursor:default}button:hover:not(:disabled){background:#c9dfd2}section,article{background:white;border:1px solid #dce6e1;border-radius:14px;padding:22px;margin-bottom:20px}.stats{display:flex;gap:20px;flex-wrap:wrap}.stats article{flex:1;min-width:220px}label,small{font-size:13px;color:#5a756c}.field{display:block;margin:15px 0}.field input{display:block;width:100%;margin-top:5px}.badge{background:#dcece1;border-radius:30px;padding:10px 18px}.notice{background:#fff2cd;padding:12px;border-radius:8px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center}.placeholder{background:#153a32;color:#9cbbb1;height:160px;border-radius:8px;display:grid;place-items:center}textarea{width:100%;min-height:100px}.warning{color:#a04b19}.table{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:12px;border-bottom:1px solid #e5ece8}code{overflow-wrap:anywhere}@media(max-width:750px){aside{position:static;width:100%;height:auto}aside small{display:none}.shell{display:block}main{margin:0;width:100%;padding:20px}aside button{display:inline-block;width:auto}.stats{display:block}}
''')
add('README.md', '''
# AquaPense local collection — first implementation

Separate modular FastAPI backend and React/TypeScript frontend. Existing RTSP script and CSV are unchanged. Sensors are explicitly disconnected; no fabricated readings.

## Run locally (two terminals)

Backend, from `backend`:
```
python -m venv .venv
.venv\\Scripts\\python -m pip install -r requirements.txt
.venv\\Scripts\\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Frontend, from `frontend`:
```
npm install
npm run dev
```
Open http://localhost:5173. Install FFmpeg and put it on PATH, or set FFMPEG_PATH to its executable before starting backend. Configure two camera hosts and passwords in Devices. Passwords are stored locally in the runtime database: protect this directory with your OS account permissions. No credentials are bundled.

## Implemented
- Camera configuration; independent RTSP/TCP recording workers and reconnects.
- Standalone/continuous collection, 60-second original-stream MKV segments, SQLite catalogue.
- Feeding/experiment markers, UTC event logs, manifests marking timing unverified.
- Local Drive OAuth from dashboard, persistent upload records, idempotent IDs, manual queue/retry.
- Low-disk pause; no automatic deletion; interrupted runs marked on restart.

## Drive testing prerequisites
Enable Google Drive API in your Google Cloud project. Create a Desktop OAuth client and add your Google account as a test user if the consent app is in testing. Save its JSON locally as `runtime/secrets/credentials.json` (create directory). Do not send passwords, tokens or client secrets in chat. Click Connect Google Drive on the edge PC and complete consent in that PC's browser. This initial loopback flow is local-only, not remote VPN OAuth. Drive scope is drive.file: existing arbitrary folders need a Picker integration; app-created folder support is the initial destination path.

## Remaining before deployment
This is a local development scaffold, not a validated collection deployment. Hardware testing is deferred as requested. Actual saved FPS, decoding quality, timeline PTS mapping and camera offset are not yet measured. No live previews, synchronized playback, sensor ingestion, automatic upload scheduler, or web OAuth/Picker yet. These must be implemented before claiming the full agreed pipeline is complete. Frontend currently polls status. Do not expose development servers to LAN/VPN until application authentication is added. Use original camera rate; no claim of 5 FPS is made until measured. Keyframe-based segment lengths may exceed 60 seconds.

## Live test information needed
Both camera IP addresses/RTSP paths; credentials entered locally in dashboard; edge PC OS and free disk; camera source FPS/resolution; Google OAuth JSON placed locally; destination selection after authentication. Sensors can follow later.
''')

# Ensure importable packages and retain empty planned module boundaries.
for p in ['core','db','modules','modules/cameras','modules/recordings','modules/drive','modules/sensors','modules/experiments','modules/synchronization','modules/storage','shared']:
    add('backend/app/'+p+'/__init__.py','')
add('backend/app/__init__.py','')
for name, content in files.items():
    dest = ROOT / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists(): raise SystemExit('Refusing to overwrite '+str(dest))
    dest.write_text(content, encoding='utf-8')
print('Created',len(files),'files in',ROOT)
