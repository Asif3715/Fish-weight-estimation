"""Execute and save notebook outputs, including partial outputs if interrupted."""
from pathlib import Path
import os
import sys
import json
import nbformat
from nbclient import NotebookClient

root = Path(__file__).resolve().parent
print('Initializing notebook execution', flush=True)
os.chdir(root)
os.environ['YOLO_CONFIG_DIR'] = str(root / '.yolo_config')
os.environ['JUPYTER_RUNTIME_DIR'] = str(root / '.jupyter' / 'runtime')
os.environ['IPYTHONDIR'] = str(root / '.ipython')
Path(os.environ['JUPYTER_RUNTIME_DIR']).mkdir(parents=True, exist_ok=True)
kernel_root = root / '.jupyter' / 'kernels' / 'aquapense'
kernel_root.mkdir(parents=True, exist_ok=True)
(kernel_root / 'kernel.json').write_text(json.dumps({
    'argv': [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
    'display_name': 'AquaPense CUDA', 'language': 'python'}))
os.environ['JUPYTER_PATH'] = str(root / '.jupyter')
path = root / 'AquaPense_CUDA_Training.ipynb'
nb = nbformat.read(path, as_version=4)
nb.metadata.kernelspec = {'display_name':'AquaPense CUDA', 'language':'python', 'name':'aquapense'}

def save_progress(**kwargs):
    nbformat.write(nb, path)
    print('Completed cell', kwargs.get('cell_index'), flush=True)

client = NotebookClient(nb, timeout=None, kernel_name='aquapense',
    resources={'metadata': {'path': str(root)}}, on_cell_executed=save_progress)
print('Starting CUDA notebook kernel', flush=True)
try:
    client.execute()
finally:
    nbformat.write(nb, path)
print('Training notebook completed.', flush=True)
