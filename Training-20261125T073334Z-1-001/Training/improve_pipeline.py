from pathlib import Path
r=Path(r'C:\Users\AFAN\Downloads\FYP\Data Pipeline')
p=r/'backend/app/modules/recordings/service.py'
s=p.read_text().replace("*folder.glob('*/ */segments.csv')", "*folder.glob('*/*/segments.csv')")
s=s.replace("self.register(chunks[:-1], run, cid)","self.register(chunks[:-1], run, cid)")
p.write_text(s)
p=r/'backend/app/modules/drive/service.py'
s=p.read_text().replace("import threading, mimetypes", "import threading, mimetypes\nfrom pathlib import Path")
s=s.replace("service = build('drive','v3',credentials=creds)", """service = build('drive','v3',credentials=creds)
            def folder(name, parent, key):
                saved = get(key)
                if saved: return saved
                meta = {'name':name, 'mimeType':'application/vnd.google-apps.folder'}
                if parent: meta['parents'] = [parent]
                fid = service.files().create(body=meta, fields='id').execute()['id']
                put(key, fid)
                return fid
            root = get('drive_folder') or folder('AquaPense Collection', None, 'drive_folder')""")
s=s.replace("# Allocate and persist an ID", """parent = root
                    parts = Path(row['path']).parts[1:-1]
                    for part in parts:
                        parent = folder(part, parent, 'folder:'+parent+':'+part)
                    # Allocate and persist an ID""")
s=s.replace("'name':row['path'].replace('\\\\','__').replace('/','__'),'parents':[get('drive_folder')]", "'name':Path(row['path']).name,'parents':[parent]")
s += '''
def scheduler(stop):
    while not stop.wait(30):
        if (SECRETS/'token.json').exists(): upload_pending()
'''
p.write_text(s)
p=r/'backend/app/modules/drive/router.py'
s=p.read_text().replace("    if not get('drive_folder'): raise HTTPException(400, 'Set a destination folder ID')\n",'')
p.write_text(s)
p=r/'backend/app/main.py'
s=p.read_text().replace('import shutil','import shutil, threading')
s=s.replace('    yield\n    recorder.stop()', '''    from app.modules.drive.service import scheduler
    stop = threading.Event()
    worker = threading.Thread(target=scheduler,args=(stop,),daemon=True)
    worker.start()
    yield
    stop.set()
    recorder.stop()
    worker.join(2)''')
s += '''
from fastapi.staticfiles import StaticFiles
from app.core.config import ROOT
dist = ROOT / 'frontend' / 'dist'
if dist.exists(): app.mount('/', StaticFiles(directory=dist, html=True), name='dashboard')
'''
p.write_text(s)
p=r/'frontend/src/main.tsx'
s=p.read_text().replace('Use a folder created by this app; arbitrary existing folders may not be accessible with the limited Drive permission.', 'Leave destination blank to create an AquaPense Collection folder automatically. Each run and camera gets its own subfolder.').replace('Upload pending / retry','Upload now / retry')
p.write_text(s)
(r/'Start-Local.ps1').write_text('''
param([string]$Python = 'C:/Users/AFAN/AppData/Local/Programs/Python/Python311/python.exe')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot 'backend')
& $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
'''.lstrip())
# Ignore the original downloaded credentials filename as well.
p=r/'.gitignore';p.write_text(p.read_text()+'\nclient_secret*.json\n')
print('Updated Drive folders, automatic retry, static dashboard serving and launcher.')
