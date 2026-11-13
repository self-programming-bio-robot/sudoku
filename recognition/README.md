# Sudoku Ink recognition training

Run from the repository root with Windows x64, CPython 3.11 and an NVIDIA
driver that supports CUDA 12.8. The PyTorch wheels include the CUDA runtime.

```powershell
py -3.11 -m venv recognition/.venv
.\recognition\.venv\Scripts\python.exe -m pip install -r recognition/requirements.txt
.\recognition\.venv\Scripts\python.exe -m unittest discover -s recognition
.\recognition\.venv\Scripts\python.exe recognition/run.py --smoke
.\recognition\.venv\Scripts\python.exe recognition/run.py
```

With an activated environment, use `python recognition/run.py`. The first
run downloads MNIST into `recognition/data/`. GPU training is required for
both modes. Smoke runs one epoch on small subsets. The full run trains for
48 epochs by default with random rotations, shifts and scale changes applied
to the training digits. MNIST zeroes are filtered out of all splits.

Use `python recognition/run.py --experiments 3 --output recognition/out/sweep`
to run three CUDA processes on the same GPU with different network widths,
augmentation ranges, and training seeds. Each process uses the same dataset
split. The sweep compares each model and every combination of their averaged
scores on validation, then evaluates only the selected model on the test set.
Selection prioritizes preserving at least 84% validation recall for each erase
gesture at zero validation false erases, then maximizing digit accuracy.
If no candidate meets the recall floor, the report still records the selected
candidate's recall. Start with `--experiments 2` on GPUs with less memory.

## Results

The full run writes to `recognition/out/full/`. Smoke results go to
`recognition/out/smoke/`. Use `--output PATH` to choose another location.

- `candidate.onnx` takes float32 images shaped `[1, 1, 28, 28]` with a dark
  background (0) and bright ink (toward 1). It returns ten sigmoid scores.
- `candidate.json` specifies the output order and strict confidence thresholds.
  Check the highest score against its own threshold. A low-confidence result
  or an erase winner with a null threshold leaves the cell as it was.
- `metrics.json` compares the candidate and the existing Android model on the
  same held-out images. The legacy result 0 represents an erase, including
  when its confidence threshold rejects a prediction. The report includes
  validation and test false-erase rates, per-digit accuracy, erase recall
  by gesture, model sizes, and single-thread CPU inference timing on the PC.

The erase threshold is selected on validation images. Test results measure
MNIST digits and synthetic gestures. Quality on real BOOX handwriting and
Android runtime compatibility require a separate device check.

The Android app packages the selected two-model ensemble from the sweep
as `app/src/main/assets/digit-recognizer.onnx` and its thresholds as
`digit-recognizer.json` in the same directory. Update both assets together.
The original `recognition/mnist.tflite` remains available for Python benchmarks.

## Collect strokes from the debug build

The existing `debug` build saves the 28×28 PNG used for inference in private
storage excluded from Android backups. Build and install it from the repository root.

```powershell
.\gradlew.bat assembleDebug
adb install -r -t app/build/outputs/apk/debug/app-debug.apk
```

A stroke over a cell filled by the player is labeled `ERASE`. Otherwise the
model's accepted digit or erase result supplies the label. Rejected inputs
are exported as `unlabeled`. These labels come from the cell state and model,
so review them before using the images for training.

Connect an authorized device with USB debugging and run from the repository
root with `adb` on PATH. The exporter uses the Python standard library.

```powershell
python recognition/export_samples.py
python recognition/export_samples.py --delete
```

Images go into `recognition/data/boox/{1..9,ERASE,unlabeled}/` by default.
Use `--output PATH` for a different destination and `--serial SERIAL` if
multiple devices are attached. With `--delete`, the script removes the
exported files from the device after the whole batch has been verified and
saved. A repeated export reuses any byte-identical files already on the PC.
