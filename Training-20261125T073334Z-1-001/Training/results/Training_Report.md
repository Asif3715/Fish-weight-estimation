# Completed CUDA training

Trained pretrained YOLO11n on the NVIDIA GeForce RTX 3050 Laptop GPU (4 GB),
using PyTorch 2.7.1+cu118 and Ultralytics 8.4.7. Training stopped early after
90 epochs, approximately 16 minutes of training. The best in-training validation
checkpoint was at epoch 65. Final evaluation reloads that checkpoint; small
metric differences from the per-epoch CSV can occur during final evaluation.

| Metric | Validation (43 images) | Test (21 images) |
|---|---:|---:|
| Precision | 96.42% | 94.12% |
| Recall | 93.68% | 95.26% |
| mAP50 | 98.45% | 98.48% |
| mAP50-95 | 72.72% | 72.45% |

The test split was evaluated after checkpoint selection. Neither test metrics
nor test predictions were used for training or checkpoint selection.
These are object detection metrics, not image classification accuracy.

## Dataset review

- 215 images, 3,555 fish boxes; all images are 2880 by 1616 pixels.
- No unreadable images, invalid boxes, orphan annotations, or exact image
  duplicates across splits were found.
- The unused COCO parent category was removed from the model class list.
- All original images and annotations were preserved.
- Reviewed sample predictions show detections around most visible fish.
  Small, overlapping fish at the aquarium's right edge remain difficult.

## Limits of these results

All reviewed samples show one aquarium and filenames indicate interleaved times
from the same recording. The supplied test split is held out from training,
but it is not an independent aquarium or recording session. High scores should
not be interpreted as generalization to new tanks, cameras or lighting.

Every supplied image has fish annotations. Empty-scene false positives are not
well tested. The 21-image test set is small. Box checks establish geometric
validity, not that every fish in every image was labeled. Perceptual similarity
warnings are dominated by the shared aquarium background.

## Saved deliverables

- `../AquaPense_CUDA_Training.ipynb`: executed notebook with outputs and plots.
- `fish_detector/weights/best.pt`: selected trained model.
- `fish_detector/results.csv` and `fish_detector/results.png`: training history.
- `metrics.json`: final metrics.
- `test_predictions/`: all 21 annotated prediction images.
- `annotation_review.jpg` and `dataset_audit.json`: annotation review.

For a stronger next evaluation, collect a separate recording session and include
empty scenes, changed lighting, motion blur and crowded fish.
