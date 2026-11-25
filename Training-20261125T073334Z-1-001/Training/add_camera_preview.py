from pathlib import Path
root=Path(r'C:\Users\AFAN\Downloads\FYP\Data Pipeline')
files={}
files['backend/app/modules/cameras/preview.py']='''"""Bounded, on-demand RTSP preview. Preview frames never enter the upload queue."""
import queue
import shutil
import subprocess
import threading
from collections import deque
from urllib.parse import quote
from fastapi import HTTPException
from app.core.config import FFMPEG

_active = set()
_lock = threading.Lock()

class Preview:
    def __init__(self, camera):
        if not camera.get('host') or not camera.get('password'):
            raise HTTPException(400, 'Save the camera address and password before starting preview.')
        if not shutil.which(FFMPEG):
            raise HTTPException(503, 'FFmpeg is unavailable. Install backend dependencies and restart the backend.')
        self.cid = camera['id']
        self.frames = queue.Queue(maxsize=2)
        self.errors = deque(maxlen=16)
        self.closed = threading.Event()
        with _lock:
            if self.cid in _active:
                raise HTTPException(409, 'Preview is already open for this camera. Stop it in the other tab first.')
            _active.add(self.cid)
        url = 'rtsp://' + quote(camera['username'], safe='') + ':' + quote(camera['password'], safe='') + '@' + camera['host'] + ':554' + camera['stream']
        command = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-rtsp_transport', 'tcp', '-rw_timeout', '10000000', '-i', url,
                   '-an', '-vf', 'fps=5,scale=640:-2', '-c:v', 'mjpeg', '-q:v', '5', '-threads', '1', '-f', 'image2pipe', 'pipe:1']
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception:
            with _lock: _active.discard(self.cid)
            raise HTTPException(503, 'Could not start the video decoder.') from None
        threading.Thread(target=self._read_errors, daemon=True).start()
        threading.Thread(target=self._read_frames, daemon=True).start()
        try:
            self.first = self.frames.get(timeout=15)
            if self.first is None: raise ValueError()
        except (queue.Empty, ValueError):
            self.close()
            error = b''.join(self.errors).lower()
            if b'401' in error or b'unauthorized' in error:
                message = 'Camera rejected the username or password. Check the local RTSP password.'
            elif b'404' in error or b'not found' in error:
                message = 'Camera did not recognize this stream path.'
            elif b'refused' in error:
                message = 'Camera refused RTSP. Enable its local RTSP service.'
            else:
                message = 'No video received. Check the camera address, hotspot connection, and RTSP settings.'
            raise HTTPException(502, message) from None

    def _put(self, frame):
        try: self.frames.put_nowait(frame)
        except queue.Full:
            try: self.frames.get_nowait()
            except queue.Empty: pass
            try: self.frames.put_nowait(frame)
            except queue.Full: pass

    def _read_errors(self):
        while not self.closed.is_set():
            line = self.process.stderr.readline(1024)
            if not line: break
            self.errors.append(line)

    def _read_frames(self):
        pending = bytearray()
        try:
            while not self.closed.is_set():
                chunk = self.process.stdout.read1(65536)
                if not chunk: break
                pending.extend(chunk)
                while True:
                    start = pending.find(b'\\xff\\xd8')
                    end = pending.find(b'\\xff\\xd9', max(start, 0) + 2)
                    if start < 0 or end < 0: break
                    self._put(bytes(pending[start:end + 2]))
                    del pending[:end + 2]
                if len(pending) > 8 * 1024 * 1024: break
        finally:
            self._put(None)

    async def stream(self, request):
        import asyncio
        frame = self.first
        try:
            while frame is not None and not self.closed.is_set():
                if await request.is_disconnected(): break
                yield b'--frame\\r\\nContent-Type: image/jpeg\\r\\nContent-Length: ' + str(len(frame)).encode() + b'\\r\\n\\r\\n' + frame + b'\\r\\n'
                # Short waits allow a disconnected browser to release its decoder promptly.
                for _ in range(100):
                    if await request.is_disconnected(): return
                    try:
                        frame = self.frames.get_nowait()
                        break
                    except queue.Empty: await asyncio.sleep(0.1)
                else: break
        finally:
            self.close()

    def close(self):
        if self.closed.is_set(): return
        self.closed.set()
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        with _lock: _active.discard(self.cid)
'''
files['frontend/src/features/cameras/CameraPreview.tsx']='''import { useEffect, useRef, useState } from "react";

export function CameraPreview({ cameraId, name }: { cameraId: string; name: string }) {
  const [playing, setPlaying] = useState(false);
  const [status, setStatus] = useState("");
  const [image, setImage] = useState("");
  const currentUrl = useRef("");
  useEffect(() => {
    if (!playing) return;
    const controller = new AbortController();
    setStatus("Connecting to camera…");
    setImage("");
    async function receive() {
      try {
        const response = await fetch(`/api/cameras/${encodeURIComponent(cameraId)}/preview`, { signal: controller.signal });
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Could not open preview.");
        }
        const reader = response.body?.getReader();
        if (!reader) throw new Error("Streaming is unavailable in this browser.");
        let buffer = new Uint8Array(0);
        while (!controller.signal.aborted) {
          const { value, done } = await reader.read();
          if (done) throw new Error("Camera stream ended. Stop and restart preview to reconnect.");
          const next = new Uint8Array(buffer.length + value.length);
          next.set(buffer); next.set(value, buffer.length); buffer = next;
          let start = -1;
          for (let i = 0; i < buffer.length - 1; i++) {
            if (buffer[i] === 255 && buffer[i + 1] === 216) start = i;
            if (start >= 0 && buffer[i] === 255 && buffer[i + 1] === 217) {
              const url = URL.createObjectURL(new Blob([buffer.slice(start, i + 2)], { type: "image/jpeg" }));
              const previous = currentUrl.current;
              currentUrl.current = url;
              setImage(url);
              if (previous) URL.revokeObjectURL(previous);
              setStatus("Live preview · up to 5 FPS");
              buffer = buffer.slice(i + 2); i = -1; start = -1;
            }
          }
          if (buffer.length > 8 * 1024 * 1024) throw new Error("Invalid video response. Restart preview.");
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setStatus(error instanceof Error ? error.message : "Preview connection failed.");
          setImage("");
          setPlaying(false);
        }
      } finally { controller.abort(); }
    }
    void receive();
    return () => {
      controller.abort();
      if (currentUrl.current) URL.revokeObjectURL(currentUrl.current);
      currentUrl.current = "";
    };
  }, [playing, cameraId]);
  return <div className="camera-preview">
    {playing && <div className="camera-preview-screen">
      {image ? <img src={image} alt={`Live view from ${name}`} /> : <span>Waiting for video…</span>}
    </div>}
    <div className="camera-preview-controls">
      <button className="button secondary small" onClick={() => { setPlaying(!playing); if (playing) { setStatus(""); setImage(""); } }}>
        {playing ? "Stop preview" : "Start live preview"}
      </button>
      <span role="status">{status}</span>
    </div>
    <p className="field-help">Preview only. Starting preview does not record or upload video.</p>
  </div>;
}
'''
for path,content in files.items(): (root/path).write_text(content,encoding='utf-8')
p=root/'backend/app/modules/cameras/router.py'
s=p.read_text(); s+='''
@router.get('/{camera_id}/preview')
def preview(camera_id: str, request: __import__('fastapi').Request):
    from fastapi.responses import StreamingResponse
    from starlette.background import BackgroundTask
    from app.modules.cameras.preview import Preview
    camera = next((c for c in get('cameras', []) if c['id'] == camera_id), None)
    if camera is None: raise HTTPException(404, 'Camera not found')
    session = Preview(camera)
    return StreamingResponse(session.stream(request), media_type='multipart/x-mixed-replace; boundary=frame',
                             headers={'Cache-Control':'no-store', 'X-Accel-Buffering':'no'}, background=BackgroundTask(session.close))
'''
s=s.replace('from fastapi import APIRouter, HTTPException','from fastapi import APIRouter, HTTPException, Request').replace("request: __import__('fastapi').Request",'request: Request');p.write_text(s)
p=root/'backend/app/core/config.py';s=p.read_text();s=s.replace("FFMPEG = os.environ.get('FFMPEG_PATH', 'ffmpeg')",'''FFMPEG = os.environ.get('FFMPEG_PATH', 'ffmpeg')
if 'FFMPEG_PATH' not in os.environ:
    import shutil
    if not shutil.which(FFMPEG):
        try:
            import imageio_ffmpeg
            FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            pass''');p.write_text(s)
p=root/'backend/requirements.txt';s=p.read_text();s+='imageio-ffmpeg>=0.6,<1\n';p.write_text(s)
p=root/'frontend/src/features/cameras/CamerasPage.tsx';s=p.read_text();s='import { CameraPreview } from "./CameraPreview";\n'+s;s=s.replace('<div className="device-footer">','<CameraPreview cameraId={c.id} name={c.name} />\n              <div className="device-footer">');p.write_text(s)
p=root/'frontend/src/styles/features.css';s=p.read_text();s+='''
.camera-preview { margin: 18px 0; }
.camera-preview-screen { aspect-ratio: 16 / 9; background: #142b35; border-radius: 10px; overflow: hidden; display: grid; place-items: center; color: #dce9e9; font-size: 12px; }
.camera-preview-screen img { width: 100%; height: 100%; object-fit: contain; }
.camera-preview-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
.camera-preview-controls [role="status"] { flex: 1; min-width: 130px; font-size: 12px; line-height: 1.6; color: #405b69; }
''';p.write_text(s)
p=root/'README.md';s=p.read_text().replace('- Live preview and synchronized playback are not implemented.','- On-demand live preview is available on each camera card (640 pixels wide, up to 5 FPS). It does not record or upload frames; synchronized playback is not implemented.').replace('and FFmpeg available on PATH.','and FFmpeg (on PATH, via `FFMPEG_PATH`, or the bundled `imageio-ffmpeg` dependency).');p.write_text(s)
print('Preview backend, modular UI, and documentation updated.')
