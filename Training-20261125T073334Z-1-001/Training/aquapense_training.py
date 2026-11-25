"""Auditable COCO conversion and CUDA fish detector training."""
from pathlib import Path
import collections
import hashlib
import json
import os
import shutil
import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'AquaPense-Anotated-Data'
DATA = ROOT / 'prepared_data'
OUTPUT = ROOT / 'results'
os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / '.yolo_config'))


def audit_summary(report):
    return {**report, 'near_cross_split_duplicates':
            {'count': len(report['near_cross_split_duplicates']),
             'examples': report['near_cross_split_duplicates'][:5],
             'full_report': str(OUTPUT / 'dataset_audit.json')}}


def prepare():
    OUTPUT.mkdir(exist_ok=True)
    report = {'splits': {}, 'errors': [], 'exact_cross_split_duplicates': [],
              'near_cross_split_duplicates': [], 'notes': [
                  'Only categories used by annotations become model classes.',
                  'Near duplicates are warnings, not proof of independent scenes.',
                  'Original splits retained; related video frames can inflate evaluation.']}
    docs = {s: json.loads((SOURCE / s / '_annotations.coco.json').read_text())
            for s in ('train', 'valid', 'test')}
    used = sorted({a['category_id'] for d in docs.values() for a in d['annotations']})
    categories = {c['id']: c['name'] for d in docs.values() for c in d['categories']}
    mapping = {cid: i for i, cid in enumerate(used)}
    report['classes'] = {mapping[c]: categories[c] for c in used}
    hashes, fingerprints, previews = {}, [], []
    for split, doc in docs.items():
        images = {im['id']: im for im in doc['images']}
        anns = collections.defaultdict(list)
        for a in doc['annotations']:
            anns[a['image_id']].append(a)
            if a['image_id'] not in images:
                report['errors'].append(f'{split}: orphan annotation {a["id"]}')
        target = 'val' if split == 'valid' else split
        for kind in ('images', 'labels'):
            (DATA / kind / target).mkdir(parents=True, exist_ok=True)
        sizes, counts, small = [], [], 0
        for idx, im in enumerate(doc['images']):
            path = SOURCE / split / im['file_name']
            with Image.open(path) as original:
                original.load()
                pic = original.convert('RGB')
            w, h = pic.size
            if (w, h) != (im['width'], im['height']):
                report['errors'].append(f'{path.name}: incorrect dimensions')
            digest = hashlib.sha256(pic.tobytes()).hexdigest()
            if digest in hashes and hashes[digest][0] != split:
                report['exact_cross_split_duplicates'].append([hashes[digest], [split, path.name]])
            hashes[digest] = [split, path.name]
            thumb = np.array(pic.convert('L').resize((9, 8)), dtype=np.int16)
            fp = thumb[:, 1:] > thumb[:, :-1]
            for old_split, old_name, old_fp in fingerprints:
                distance = int(np.count_nonzero(fp != old_fp))
                if old_split != split and distance <= 4:
                    report['near_cross_split_duplicates'].append([old_split, old_name, split, path.name, distance])
            fingerprints.append((split, path.name, fp))
            lines = []
            for a in anns[im['id']]:
                x, y, bw, bh = a['bbox']
                if not all(np.isfinite([x, y, bw, bh])) or bw <= 0 or bh <= 0 or x < 0 or y < 0 or x+bw > w+1 or y+bh > h+1:
                    report['errors'].append(f'{split}/{path.name}: invalid box {a["id"]}')
                    continue
                x2, y2 = min(w, x+bw), min(h, y+bh)
                lines.append(f'{mapping[a["category_id"]]} {(x+x2)/2/w:.8f} {(y+y2)/2/h:.8f} {(x2-x)/w:.8f} {(y2-y)/h:.8f}')
                small += int(bw/w*640 < 16 or bh/h*640 < 16)
            filename = f'{idx:05d}{path.suffix.lower()}'
            destination = DATA / 'images' / target / filename
            if not destination.exists():
                shutil.copy2(path, destination)
            (DATA / 'labels' / target / Path(filename).with_suffix('.txt')).write_text('\n'.join(lines))
            sizes.append([w, h]); counts.append(len(lines))
            if idx < 4:
                draw = ImageDraw.Draw(pic)
                for a in anns[im['id']]:
                    x,y,bw,bh = a['bbox']; draw.rectangle([x,y,x+bw,y+bh], outline='lime', width=3)
                tile = ImageOps.pad(pic, (480, 280))
                ImageDraw.Draw(tile).text((8,8), f'{split}: {len(lines)} fish', fill='yellow')
                previews.append(tile)
        report['splits'][split] = {'images': len(images), 'boxes': sum(counts),
            'empty_images': counts.count(0), 'image_sizes': dict(collections.Counter(map(str,sizes))),
            'boxes_under_16px_at_640': small}
    canvas = Image.new('RGB', (480*4, 280*3))
    for i, tile in enumerate(previews): canvas.paste(tile, ((i%4)*480, (i//4)*280))
    canvas.save(OUTPUT / 'annotation_review.jpg')
    (OUTPUT / 'dataset_audit.json').write_text(json.dumps(report, indent=2))
    if report['errors'] or report['exact_cross_split_duplicates']:
        raise ValueError('Dataset integrity failure; see results/dataset_audit.json')
    names = '\n'.join(f'  {mapping[c]}: {categories[c]}' for c in used)
    config = DATA / 'data.yaml'
    config.write_text(f'path: {DATA.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n{names}\n')
    return report


def train(epochs=120):
    import torch
    from ultralytics import YOLO
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is required. Install a CUDA-enabled PyTorch build.')
    print('GPU:', torch.cuda.get_device_name(0), 'PyTorch:', torch.__version__)
    model = YOLO('yolo11n.pt')
    model.train(data=str(DATA/'data.yaml'), epochs=epochs, patience=25,
        imgsz=640, batch=4, device=0, workers=0, amp=True,
        optimizer='AdamW', lr0=0.001, lrf=0.01, weight_decay=0.0005,
        warmup_epochs=3, cos_lr=True, mosaic=0.5, close_mosaic=15,
        degrees=5, translate=0.1, scale=0.3, fliplr=0.5, flipud=0.0,
        hsv_h=0.015, hsv_s=0.4, hsv_v=0.3, seed=42, deterministic=True,
        cache=False, project=str(OUTPUT), name='fish_detector', exist_ok=False,
        plots=True, save=True)
    return str(model.trainer.best)


def evaluate(best):
    from ultralytics import YOLO
    model = YOLO(best)
    results = {}
    for split in ('val', 'test'):
        metrics = model.val(data=str(DATA/'data.yaml'), split=split, imgsz=640,
            batch=4, device=0, workers=0, plots=True, project=str(OUTPUT), name=f'{split}_evaluation')
        results[split] = {k: float(v) for k,v in metrics.results_dict.items()}
    model.predict(source=str(DATA/'images/test'), imgsz=640, device=0, conf=0.25,
        save=True, project=str(OUTPUT), name='test_predictions')
    (OUTPUT/'metrics.json').write_text(json.dumps(results, indent=2))
    return results


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(audit_summary(prepare()), indent=2))
    if not args.audit_only:
        print(evaluate(train()))
