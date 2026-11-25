# AquaPense: fish size, weight and feed

Pipeline: trained YOLO11n detector → quality filter → body length (cm) → weight (g) → daily feed (g).

## Run

```bash
.venv/bin/streamlit run app.py          # interface at http://localhost:8501
.venv/bin/python evaluate.py            # report on all 215 images -> results_weight/
```

## Files

- `fishsize/core.py`: measurement pipeline (detector wrapper, filters, length, weight, feed)
- `app.py`: Streamlit interface (upload images, set tank width and feed rate)
- `evaluate.py`: batch evaluation, writes CSVs, `summary.json` and figures to `results_weight/`

## Before trusting the grams

1. Measure the tank's inner width and enter it in the sidebar (default 90 cm is a placeholder).
2. Weigh and measure 3–5 fish to check the estimates.
