from pathlib import Path
root=Path(r'C:\Users\AFAN\Downloads\FYP\Data Pipeline')
p=root/'backend/app/modules/cameras/router.py';s=p.read_text();s+='''
@router.post('/connect')
def connect_camera(camera: Camera):
    from app.modules.cameras.preview import Preview
    from app.modules.recordings.service import recorder
    if recorder.active: raise HTTPException(409, 'Stop recording before changing cameras')
    old = get('cameras', [])
    candidate = camera.model_dump()
    previous = next((c for c in old if c['id'] == camera.id), {})
    if not candidate['password']: candidate['password'] = previous.get('password', '')
    if not candidate['stream'].startswith('/'):
        raise HTTPException(400, 'Stream path must start with /')
    session = Preview(candidate)
    session.close()
    rows = [Camera(**(candidate if c['id'] == camera.id else c)) for c in old]
    if not previous: rows.append(Camera(**candidate))
    save(rows)
    return {'saved': True, 'verified': True}
''';p.write_text(s)
p=root/'frontend/src/hooks/useWorkspaceController.ts';s=p.read_text();s=s.replace('  async function refresh() {','  const [previewRequest, setPreviewRequest] = useState<{ id: string; revision: number } | null>(null);\n  async function refresh() {');start=s.index('    const next = cameras.some');end=s.index('\n  const enabled',start)
s=s[:start]+'''    const saved = { ...editor };
    if (await action(() => api("cameras/connect", "POST", saved), "Camera verified and saved. Opening live preview.")) {
      setCameras(await api<Camera[]>("cameras"));
      setEditor(null);
      setPage("Cameras");
      setPreviewRequest({ id: saved.id, revision: Date.now() });
    }
  }
'''+s[end:];s=s.replace('    page,\n','    previewRequest,\n    page,\n');p.write_text(s)
p=root/'frontend/src/features/cameras/CamerasPage.tsx';s=p.read_text().replace('setShowSecret, enabled }','setShowSecret, enabled, previewRequest }').replace('<CameraPreview cameraId={c.id} name={c.name} />','<CameraPreview key={`${c.id}:${previewRequest?.id === c.id ? previewRequest.revision : 0}`} cameraId={c.id} name={c.name} autoStart={previewRequest?.id === c.id} />');p.write_text(s)
p=root/'frontend/src/features/cameras/CameraPreview.tsx';s=p.read_text().replace('{ cameraId, name }: { cameraId: string; name: string }','{ cameraId, name, autoStart = false }: { cameraId: string; name: string; autoStart?: boolean }').replace('useState(false)','useState(autoStart)',1);p.write_text(s)
p=root/'frontend/src/features/cameras/CameraDialog.tsx';s=p.read_text().replace('    saveCamera,','    saveCamera,\n    notice,');s=s.replace('<form onSubmit={saveCamera}>','<form onSubmit={saveCamera}>\n          {notice?.error && <p role="alert" className="field-help">{notice.text}</p>}');s=s.replace('{busy ? "Saving…" : "Save camera"}','{busy ? "Verifying camera…" : "Verify & save camera"}');p.write_text(s)
p=root/'frontend/src/features/overview/OverviewPage.tsx';s=p.read_text().replace('Live preview coming next','Live preview available in Cameras').replace('Recording status is shown below','Open Manage to view the live feed');p.write_text(s)
p=root/'README.md';s=p.read_text().replace('Repeat for additional cameras.','Click **Verify & save camera** to authenticate and decode a frame before saving; a successful save opens live preview on the Cameras page. Failed verification keeps the form open without replacing saved settings. Repeat for additional cameras.');p.write_text(s)
print('Save-time verification and automatic preview added.')
