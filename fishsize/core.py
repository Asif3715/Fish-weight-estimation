"""Fish detection -> length (cm) -> weight (g) -> feed (g/day).

Pipeline
1. Trained YOLO11n detector (your best.pt) finds every fish.
2. Each box is checked: fish near the side glass (reflections, distortion),
   overlapping fish and clipped fish are counted but NOT measured.
3. Inside each measurable box, the fish body is segmented by colour and its
   length is taken along the body's main axis (works for tilted fish, unlike
   the box width).
4. Pixels -> cm with a one-camera depth bracket: the tank's front edge and the
   back wall have the same real width, so they give the scale for a fish at
   the front glass and at the back wall. The fish's true length lies between
   the two; the midpoint is reported as the estimate.
5. Weight from the goldfish length-weight relationship W = a * L^b
   (FishBase Bayesian estimate for Carassius auratus, TL in cm, W in g).
"""
from dataclasses import dataclass, field

import cv2
import numpy as np

# ---------------------------------------------------------------- settings
LWR_A, LWR_B = 0.01288, 3.04

@dataclass
class Calibration:
    tank_width_cm: float = 90.0        # MEASURE THIS: inner width of the tank
    front_span_frac: float = 0.94      # front glass width / image width
    back_span_frac: float = 0.81       # back wall width / image width
    # measurable zone (fractions of image) - excludes side glass & overlays
    zone: tuple = (0.07, 0.04, 0.89, 0.90)   # x0, y0, x1, y1

    def px_per_cm(self, img_w):
        front = self.front_span_frac * img_w / self.tank_width_cm
        back = self.back_span_frac * img_w / self.tank_width_cm
        return front, back


@dataclass
class Fish:
    box: tuple                 # x1, y1, x2, y2 (original pixels)
    conf: float
    status: str                # "measured" or reason it was skipped
    length_px: float = np.nan
    method: str = ""
    length_cm: float = np.nan
    length_cm_min: float = np.nan
    length_cm_max: float = np.nan
    weight_g: float = np.nan
    weight_g_min: float = np.nan
    weight_g_max: float = np.nan
    contour: np.ndarray = field(default=None, repr=False)


def weight_from_length(cm):
    return LWR_A * np.power(cm, LWR_B)


def _iou_matrix(b):
    x1 = np.maximum(b[:, None, 0], b[None, :, 0]); y1 = np.maximum(b[:, None, 1], b[None, :, 1])
    x2 = np.minimum(b[:, None, 2], b[None, :, 2]); y2 = np.minimum(b[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    # overlap relative to the smaller box, so a small fish behind a big one counts
    return inter / np.minimum(area[:, None], area[None, :]).clip(1)


def body_length(img, box):
    """Length along the fish's main axis, from a colour mask inside the box."""
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        return np.nan, "none", None, np.nan, np.nan
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    # orange/red/yellow body + pale (white-orange) patches
    orange = cv2.inRange(hsv, (0, 110, 110), (30, 255, 255)) | cv2.inRange(hsv, (170, 110, 110), (180, 255, 255))
    mask = cv2.morphologyEx(orange, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    bw, bh = x2 - x1, y2 - y1
    fallback = max(bw, bh)
    box_elong = max(bw, bh) / max(min(bw, bh), 1)
    if not cnts:
        return fallback, "box", None, box_elong, 0.0
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.15 * bw * bh:
        return fallback, "box", None, box_elong, 0.0
    pts = c.reshape(-1, 2).astype(float)
    pts_c = pts - pts.mean(0)
    _, vecs = np.linalg.eigh(np.cov(pts_c.T))
    length = np.ptp(pts_c @ vecs[:, 1]) + 1
    elong = length / (np.ptp(pts_c @ vecs[:, 0]) + 1)
    tilt = np.degrees(np.arctan2(abs(vecs[1, 1]), abs(vecs[0, 1])))  # 0 = horizontal
    # mask often misses translucent tail: never shorter than 85% of box long side
    length = max(length, 0.85 * fallback)
    return float(min(length, np.hypot(bw, bh))), "mask", c + [x1, y1], float(elong), float(tilt)


def analyse(img, detections, cal: Calibration, overlap_thr=0.5, min_elong=1.9, max_tilt_deg=50):
    """detections: array Nx5 (x1,y1,x2,y2,conf) in original pixels."""
    h, w = img.shape[:2]
    det = np.asarray(detections, float).reshape(-1, 5)
    zx0, zy0, zx1, zy1 = cal.zone[0] * w, cal.zone[1] * h, cal.zone[2] * w, cal.zone[3] * h
    ov = _iou_matrix(det[:, :4]) if len(det) else np.zeros((0, 0))
    np.fill_diagonal(ov, 0)
    front, back = cal.px_per_cm(w)
    mid = 2 / (1 / front + 1 / back)  # scale for a fish at mid-depth
    out = []
    for i, (x1, y1, x2, y2, conf) in enumerate(det):
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        if not (zx0 <= cx <= zx1 and zy0 <= cy <= zy1):
            status = "skipped: side glass / edge"
        elif ov.shape[0] and ov[i].max() > overlap_thr:
            status = "skipped: overlapping"
        elif x1 <= 2 or y1 <= 2 or x2 >= w - 2 or y2 >= h - 2:
            status = "skipped: clipped"
        else:
            status = "measured"
        f = Fish((x1, y1, x2, y2), float(conf), status)
        if status == "measured":
            f.length_px, f.method, f.contour, elong, tilt = body_length(img, f.box)
            if not (elong >= min_elong and tilt <= max_tilt_deg):
                # head-on, turning or diving fish are foreshortened -> too short
                f.status, f.contour = "skipped: not side-on", None
                out.append(f)
                continue
            f.length_cm = f.length_px / mid
            f.length_cm_min = f.length_px / front   # if the fish is at the front glass
            f.length_cm_max = f.length_px / back    # if the fish is at the back wall
            f.weight_g = weight_from_length(f.length_cm)
            f.weight_g_min = weight_from_length(f.length_cm_min)
            f.weight_g_max = weight_from_length(f.length_cm_max)
        out.append(f)
    return out


def summarise(fishes, fish_count=None, feed_rate_pct=2.0, meals=2):
    m = [f for f in fishes if f.status == "measured"]
    n_det = len(fishes)
    count = fish_count or n_det
    if not m:
        return dict(detected=n_det, measured=0, count_used=count)
    L = np.array([f.length_cm for f in m]); W = np.array([f.weight_g for f in m])
    Wlo = np.array([f.weight_g_min for f in m]); Whi = np.array([f.weight_g_max for f in m])
    mean_w = float(np.mean(W))
    biomass = mean_w * count
    feed = biomass * feed_rate_pct / 100
    return dict(
        detected=n_det, measured=len(m), count_used=count,
        mean_length_cm=float(np.mean(L)), median_length_cm=float(np.median(L)),
        mean_weight_g=mean_w, mean_weight_g_range=(float(np.mean(Wlo)), float(np.mean(Whi))),
        biomass_g=biomass, biomass_g_range=(float(np.mean(Wlo)) * count, float(np.mean(Whi)) * count),
        feed_g_day=feed, feed_g_meal=feed / meals, feed_rate_pct=feed_rate_pct, meals=meals,
    )


def draw(img, fishes):
    out = img.copy()
    for f in fishes:
        x1, y1, x2, y2 = [int(v) for v in f.box]
        if f.status == "measured":
            col = (60, 220, 60)
            if f.contour is not None:
                cv2.drawContours(out, [f.contour.astype(np.int32)], -1, (255, 255, 0), 2)
            label = f"{f.length_cm:.1f}cm {f.weight_g:.1f}g"
        else:
            col, label = (150, 150, 150), "-"
        cv2.rectangle(out, (x1, y1), (x2, y2), col, 3 if f.status == "measured" else 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
        cv2.rectangle(out, (x1, y1 - th - 10), (x1 + tw + 6, y1), col, -1)
        cv2.putText(out, label, (x1 + 3, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2, cv2.LINE_AA)
    return out


class FishWeigher:
    def __init__(self, weights, conf=0.35, imgsz=640):
        from ultralytics import YOLO
        self.model = YOLO(weights)
        self.conf, self.imgsz = conf, imgsz

    def detect(self, img):
        r = self.model.predict(img, imgsz=self.imgsz, conf=self.conf, verbose=False)[0]
        return np.hstack([r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()[:, None]])

    def __call__(self, img, cal=None):
        return analyse(img, self.detect(img), cal or Calibration())
