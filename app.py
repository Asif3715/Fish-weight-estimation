"""AquaPense - fish size, weight and feed estimator.

    .venv/bin/streamlit run app.py
"""
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import streamlit as st

from fishsize.core import FishWeigher, Calibration, summarise, draw, weight_from_length

WEIGHTS = "Training-20261125T073334Z-1-001/Training/results/fish_detector/weights/best.pt"
SAMPLES = Path("Training-20261125T073334Z-1-001/Training/prepared_data/images/test")

st.set_page_config(page_title="AquaPense – Fish Weight & Feed", page_icon="🐟", layout="wide")


@st.cache_resource
def load_model(conf):
    return FishWeigher(WEIGHTS, conf=conf)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Tank calibration")
    tank_cm = st.number_input("Tank inner width (cm)", 20.0, 300.0, 90.0, 1.0,
                              help="Measure the inside width of the tank. All cm/g values scale with this.")
    with st.expander("Advanced"):
        front = st.slider("Front glass width / image width", 0.5, 1.0, 0.94, 0.01)
        back = st.slider("Back wall width / image width", 0.4, 1.0, 0.81, 0.01)
        conf = st.slider("Detector confidence", 0.1, 0.9, 0.35, 0.05)
    st.header("Feeding")
    known = st.number_input("Number of fish in tank (0 = use detections)", 0, 500, 0)
    rate = st.slider("Feed rate (% of body weight per day)", 0.5, 5.0, 2.0, 0.1)
    meals = st.number_input("Meals per day", 1, 6, 2)

cal = Calibration(tank_width_cm=tank_cm, front_span_frac=front, back_span_frac=back)
model = load_model(conf)

st.title("🐟 AquaPense — fish size, weight & feed estimator")
st.caption("YOLO11n fish detector → body-length measurement → goldfish length–weight model "
           "(W = 0.01288·L³·⁰⁴) → daily feed")

up = st.file_uploader("Upload one or more tank images (several frames give a steadier estimate)",
                      type=["jpg", "jpeg", "png"], accept_multiple_files=True)
images = []
if up:
    for f in up:
        images.append((f.name, cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)))
else:
    samples = sorted(SAMPLES.glob("*.jpg"))
    if samples:
        pick = st.selectbox("…or try a sample test image", [p.name for p in samples])
        images.append((pick, cv2.imread(str(SAMPLES / pick))))

if not images:
    st.stop()

all_fish, per_image_counts = [], []
for name, img in images:
    fishes = model(img, cal)
    all_fish.extend(fishes)
    per_image_counts.append(len(fishes))

det_count = int(np.median(per_image_counts))
s = summarise(all_fish, fish_count=known or det_count, feed_rate_pct=rate, meals=meals)
s["detected"] = det_count

# ------------------------------------------------------------------ results
c = st.columns(5)
c[0].metric("Fish detected", det_count)
c[1].metric("Measured (side-on)", s["measured"])
if s["measured"]:
    c[2].metric("Avg length", f"{s['mean_length_cm']:.1f} cm")
    lo, hi = s["mean_weight_g_range"]
    c[3].metric("Avg weight", f"{s['mean_weight_g']:.1f} g", help=f"depth range {lo:.1f}–{hi:.1f} g")
    c[4].metric("Total biomass", f"{s['biomass_g']:.0f} g",
                help=f"{s['count_used']} fish × avg weight; depth range "
                     f"{s['biomass_g_range'][0]:.0f}–{s['biomass_g_range'][1]:.0f} g")

    st.success(f"**Recommended feed: {s['feed_g_day']:.2f} g/day** "
               f"→ {s['feed_g_meal']:.2f} g per meal × {meals} meals "
               f"({rate:.1f}% of {s['biomass_g']:.0f} g biomass, {s['count_used']} fish)")
else:
    st.warning("No fish could be measured (all were overlapping, turned or near the side glass). "
               "Try another frame or upload several.")

tab1, tab2, tab3 = st.tabs(["Annotated image", "Per-fish table", "How it works"])
with tab1:
    name, img = images[0]
    fishes = model(img, cal)
    st.image(cv2.cvtColor(draw(img, fishes), cv2.COLOR_BGR2RGB), caption=f"{name} — green: measured, grey: counted only",
             use_container_width=True)
    if len(images) > 1:
        st.caption(f"Showing the first of {len(images)} images; metrics above pool all of them.")
with tab2:
    df = pd.DataFrame([dict(status=f.status, confidence=round(f.conf, 2),
                            length_cm=round(f.length_cm, 1), length_range_cm=
                            f"{f.length_cm_min:.1f}–{f.length_cm_max:.1f}" if f.status == "measured" else "",
                            weight_g=round(f.weight_g, 1)) for f in all_fish])
    st.dataframe(df, use_container_width=True)
    st.download_button("Download CSV", df.to_csv(index=False), "fish_measurements.csv")
with tab3:
    st.markdown(f"""
1. **Detection** – your trained YOLO11n model (test mAP50 98.5 %) finds every fish.
2. **Quality filter** – fish near the side glass (reflections), overlapping fish, and fish that are
   turned toward the camera are *counted* but not *measured*, because their apparent length is wrong.
3. **Length** – the fish body is segmented by colour inside its box and measured along its main axis.
4. **Pixels → cm** – the front glass and the back wall have the same real width ({tank_cm:.0f} cm), so they
   give the scale for a fish at the front and at the back. A single camera can't tell how deep the fish is,
   so the estimate uses mid-depth and the range shows front ↔ back.
5. **Weight** – goldfish length–weight relationship (FishBase): W = 0.01288 × L^3.04.
6. **Feed** – fish count × average weight × feed rate.

**Limitation:** one camera → depth uncertainty of roughly ±20 % in weight per fish. Averaging many frames
reduces random error but not the calibration error; validate by weighing a few fish.
""")
    L = np.linspace(3, 15, 50)
    st.line_chart(pd.DataFrame({"weight (g)": weight_from_length(L)}, index=pd.Index(L.round(1), name="length (cm)")))
