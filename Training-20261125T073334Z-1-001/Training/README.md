# AquaPense CUDA training

Open `AquaPense_CUDA_Training.ipynb` to review and run the complete workflow.
`Run-Training.ps1` executes the notebook and saves its outputs using the existing
Python 3.11 installation on this computer. Each training run creates a new result
directory; it does not overwrite the original annotations.

The dataset has 151 training images (2,490 boxes), 43 validation images (712 boxes),
and 21 test images (353 boxes). The only annotated class is `fish`; the unused
`AquaPense` parent category is excluded. COCO boxes are converted to normalized
YOLO boxes in `prepared_data`.

The RTX 3050 Laptop GPU has 4 GB of VRAM. Training explicitly requires CUDA and
uses pretrained YOLO11n, batch 4, 640-pixel inputs, mixed precision, Windows-safe
data loading, and validation early stopping. If another application consumes
GPU memory, close it or lower batch to 2 in `aquapense_training.py`.

Outputs:

- `results/dataset_audit.json`: integrity checks and similarity warnings.
- `results/annotation_review.jpg`: sample annotated images from all splits.
- `results/fish_detector*/weights/best.pt`: best validation checkpoint.
- `results/fish_detector*/results.csv`: per-epoch metrics and losses.
- `results/metrics.json`: final validation and test metrics.
- `results/test_predictions*`: test images with predicted boxes.

All reviewed images show the same aquarium. The image filenames indicate nearby
times in the same recording; the supplied splits interleave those times.
Perceptual image hashes are strongly influenced by the static background, so
their warnings do not mean the fish positions are duplicates. Scores on these
splits describe this aquarium and should not be presented as evidence of
performance on new tanks or recording sessions. Collect separate recording
sessions for a stronger independent evaluation.

Small, overlapping, edge-clipped and blurred fish are the main visual challenges.
344 boxes become narrower or shorter than 16 pixels at 640-pixel input width.
The audit verifies box geometry, but does not establish annotation completeness
for every image. Review missed detections and false positives after training.

Training API reference: https://docs.ultralytics.com/modes/train/
