"""Run the size/weight pipeline on every prepared image and write a report.

    .venv/bin/python evaluate.py

Outputs in results_weight/: per_fish.csv, per_image.csv, summary.json,
figures (*.png) and annotated test images.
"""
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fishsize.core import FishWeigher, Calibration, summarise, draw

ROOT = Path("Training-20261125T073334Z-1-001/Training")
WEIGHTS = ROOT / "results/fish_detector/weights/best.pt"
DATA = ROOT / "prepared_data"
OUT = Path("results_weight")


def main():
    (OUT / "annotated").mkdir(parents=True, exist_ok=True)
    weigher, cal = FishWeigher(str(WEIGHTS)), Calibration()
    fish_rows, img_rows = [], []
    for split in ["train", "val", "test"]:
        for p in sorted((DATA / "images" / split).glob("*.jpg")):
            img = cv2.imread(str(p))
            fishes = weigher(img, cal)
            lab = DATA / "labels" / split / (p.stem + ".txt")
            gt = sum(1 for _ in open(lab)) if lab.exists() else np.nan
            s = summarise(fishes)
            img_rows.append(dict(split=split, image=p.name, gt_count=gt, detected=s["detected"],
                                 measured=s["measured"], mean_length_cm=s.get("mean_length_cm"),
                                 mean_weight_g=s.get("mean_weight_g")))
            for f in fishes:
                fish_rows.append(dict(split=split, image=p.name, status=f.status, conf=f.conf,
                                      length_px=f.length_px, length_cm=f.length_cm,
                                      length_cm_min=f.length_cm_min, length_cm_max=f.length_cm_max,
                                      weight_g=f.weight_g, method=f.method))
            if split == "test":
                cv2.imwrite(str(OUT / "annotated" / p.name), draw(img, fishes))
    fish, imgs = pd.DataFrame(fish_rows), pd.DataFrame(img_rows)
    fish.to_csv(OUT / "per_fish.csv", index=False)
    imgs.to_csv(OUT / "per_image.csv", index=False)

    m = fish[fish.status == "measured"]
    test = imgs[imgs.split == "test"]
    err = test.detected - test.gt_count
    summary = {
        "images": len(imgs),
        "detections": int(len(fish)),
        "measured_fish": int(len(m)),
        "skip_reasons": fish.status.value_counts().to_dict(),
        "count_test_MAE": float(err.abs().mean()),
        "count_test_mean_bias": float(err.mean()),
        "count_test_MAPE_pct": float((err.abs() / test.gt_count).mean() * 100),
        "length_cm": m.length_cm.describe().round(2).to_dict(),
        "weight_g": m.weight_g.describe().round(2).to_dict(),
        "per_image_mean_weight_g": {"mean": float(imgs.mean_weight_g.mean()),
                                    "std": float(imgs.mean_weight_g.std()),
                                    "cv_pct": float(imgs.mean_weight_g.std() / imgs.mean_weight_g.mean() * 100)},
        "pooled_mean_weight_g": float(m.weight_g.mean()),
        "pooled_mean_weight_g_depth_range": [float(m.length_cm_min.pow(3.04).mul(0.01288).mean()),
                                             float(m.length_cm_max.pow(3.04).mul(0.01288).mean())],
        "median_gt_count": float(imgs.gt_count.median()),
        "calibration": {"tank_width_cm": cal.tank_width_cm, "front_span_frac": cal.front_span_frac,
                        "back_span_frac": cal.back_span_frac},
    }
    n = summary["median_gt_count"]
    summary["biomass_g_estimate"] = summary["pooled_mean_weight_g"] * n
    summary["feed_g_day_at_2pct"] = summary["biomass_g_estimate"] * 0.02
    json.dump(summary, open(OUT / "summary.json", "w"), indent=2)

    fig, ax = plt.subplots(1, 3, figsize=(15, 4))
    ax[0].hist(m.length_cm, bins=30, color="#e8833a"); ax[0].set(title="Estimated fish length", xlabel="cm", ylabel="fish detections")
    ax[1].hist(m.weight_g, bins=30, color="#3a7be8"); ax[1].set(title="Estimated fish weight", xlabel="g")
    ax[2].scatter(test.gt_count, test.detected, color="#2a9d5c")
    lim = [0, max(test.gt_count.max(), test.detected.max()) + 2]
    ax[2].plot(lim, lim, "k--", lw=1); ax[2].set(title="Fish count, test images", xlabel="labelled", ylabel="detected")
    fig.tight_layout(); fig.savefig(OUT / "report_figures.png", dpi=120)

    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.plot(imgs.mean_weight_g.values, ".", alpha=.6)
    ax.axhline(summary["pooled_mean_weight_g"], color="r", label="pooled mean")
    ax.set(title="Mean fish weight estimated from each single image", xlabel="image", ylabel="g"); ax.legend()
    fig.tight_layout(); fig.savefig(OUT / "per_image_stability.png", dpi=120)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
