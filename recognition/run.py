import argparse
import copy
import json
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace
from itertools import combinations
from pathlib import Path

# cuBLAS requires this setting for deterministic CUDA matrix operations.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import onnx
import onnxruntime as ort
import torch
from ai_edge_litert.interpreter import Interpreter
from torch import nn
from torch.nn import functional as F
from torch.utils.data import DataLoader, TensorDataset

from data import IMAGE_SIZE, LABELS, Samples, load_samples
from evaluation import (
    DIGIT_THRESHOLD,
    calibrate_erase_threshold,
    candidate_actions,
    legacy_actions,
    measure_inference,
    summarize,
)


ROOT = Path(__file__).resolve().parent
LEGACY_MODEL = ROOT.parent / "app/src/main/assets/mnist.tflite"
SEED = 1729
OPSET = 17
ONNX_INPUT_SHAPE = (1, 1, IMAGE_SIZE, IMAGE_SIZE)
PARITY_TOLERANCE = 0.0001


@dataclass(frozen=True)
class TrainingConfig:
    epochs: int = 48
    width: int = 32
    hidden: int = 96
    angle: float = 0.20
    shift: float = 0.14
    scale: float = 0.15
    seed: int = SEED


EXPERIMENTS = {
    "affine": TrainingConfig(),
    "wide": TrainingConfig(epochs=48, width=40, hidden=128, angle=0.16, seed=1730),
    "strong-affine": TrainingConfig(epochs=56, angle=0.26, shift=0.18, scale=0.20, seed=1731),
}


def image_tensor(samples: Samples) -> torch.Tensor:
    return torch.from_numpy(samples.images[:, None]).to(torch.float32).div_(255)


def augment_digits(images: torch.Tensor, targets: torch.Tensor, config: TrainingConfig) -> torch.Tensor:
    # Keep synthetic gestures as generated and vary only the handwritten digits.
    digits = targets[:, :-1].any(dim=1)
    random = torch.rand((len(images), 4), device=images.device) * 2 - 1
    angle = random[:, 0] * config.angle
    scale = 1 + random[:, 1] * config.scale
    cosine = angle.cos() * scale
    sine = angle.sin() * scale
    shift_x, shift_y = (random[:, 2:] * config.shift).unbind(dim=1)
    transform = torch.stack((cosine, -sine, shift_x, sine, cosine, shift_y), dim=1)
    grid = F.affine_grid(transform.reshape(-1, 2, 3), images.shape, align_corners=False)
    warped = F.grid_sample(images, grid, align_corners=False)
    return torch.where(digits[:, None, None, None], warped, images)


def make_network(config: TrainingConfig) -> nn.Module:
    width = config.width
    return nn.Sequential(
        nn.Conv2d(1, width, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.Conv2d(width, width, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(width, 2 * width, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.Conv2d(2 * width, 2 * width, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Flatten(),
        nn.Linear(2 * width * 7 * 7, config.hidden),
        nn.ReLU(),
        nn.Dropout(0.15),
        nn.Linear(config.hidden, len(LABELS)),
    )


def train_model(train: Samples, validation: Samples, config: TrainingConfig) -> nn.Module:
    torch.manual_seed(config.seed)
    network = make_network(config).cuda()
    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.AdamW(network.parameters(), lr=0.001)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=config.epochs, eta_min=0.00005)
    train_data = TensorDataset(image_tensor(train), torch.from_numpy(train.targets()))
    batches = DataLoader(
        train_data,
        batch_size=256,
        shuffle=True,
        pin_memory=True,
        generator=torch.Generator().manual_seed(config.seed),
    )
    validation_images = image_tensor(validation).cuda()
    validation_targets = torch.from_numpy(validation.targets()).cuda()
    best_rank = None
    best_weights = None
    for epoch in range(config.epochs):
        network.train()
        for images, targets in batches:
            targets = targets.cuda(non_blocking=True)
            images = augment_digits(images.cuda(non_blocking=True), targets, config)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(network(images), targets)
            loss.backward()
            optimizer.step()
        schedule.step()

        network.eval()
        with torch.inference_mode():
            logits = torch.cat([network(batch) for batch in validation_images.split(512)])
            loss = criterion(logits, validation_targets).item()
            scores = logits.sigmoid().cpu().numpy()
        rank = validation_rank(scores, validation, loss)
        print(f"Epoch {epoch + 1}/{config.epochs} | validation digits {rank[1]:.2%} | erase {rank[2]:.2%}", flush=True)
        if np.isfinite(loss) and (best_rank is None or rank > best_rank):
            best_rank = rank
            best_weights = copy.deepcopy(network.state_dict())

    if best_weights is None:
        raise RuntimeError("Training did not produce finite validation loss")
    network.load_state_dict(best_weights)
    return nn.Sequential(network.cpu(), nn.Sigmoid()).eval()


def validation_rank(scores: np.ndarray, samples: Samples, loss: float = 0.0) -> tuple:
    threshold = calibrate_erase_threshold(scores, samples.labels)
    actions = candidate_actions(scores, threshold)
    digits = samples.kinds == "digit"
    correct = actions == samples.labels
    erase_recall = min(float(correct[samples.kinds == kind].mean()) for kind in ("cross", "scribble"))
    return erase_recall >= 0.84, float(correct[digits].mean()), erase_recall, -loss


class Ensemble(nn.Module):
    def __init__(self, models: list[nn.Module]):
        super().__init__()
        self.models = nn.ModuleList(models)

    def forward(self, images):
        return torch.stack([model(images) for model in self.models]).mean(dim=0)


def export_model(model: nn.Module, path: Path):
    torch.onnx.export(
        model,
        (torch.zeros(ONNX_INPUT_SHAPE),),
        str(path),
        input_names=["image"],
        output_names=["scores"],
        opset_version=OPSET,
        dynamo=False,
    )
    onnx.checker.check_model(str(path), full_check=True)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
    model_input, = session.get_inputs()
    model_output, = session.get_outputs()
    if tuple(model_input.shape) != ONNX_INPUT_SHAPE or model_input.type != "tensor(float)":
        raise ValueError("Unexpected ONNX input signature")
    if model_output.shape != [1, len(LABELS)] or model_output.type != "tensor(float)":
        raise ValueError("Unexpected ONNX output signature")

    def predict(image: np.ndarray) -> np.ndarray:
        return session.run(["scores"], {"image": image.reshape(ONNX_INPUT_SHAPE)})[0][0]

    return predict


def legacy_predictor():
    interpreter = Interpreter(model_path=str(LEGACY_MODEL), num_threads=1)
    interpreter.allocate_tensors()
    input_info, = interpreter.get_input_details()
    output_info, = interpreter.get_output_details()
    expected_shape = (1, IMAGE_SIZE, IMAGE_SIZE)
    if tuple(input_info["shape"]) != expected_shape or input_info["dtype"] != np.float32:
        raise ValueError("Unexpected legacy TFLite input signature")
    if tuple(output_info["shape"]) != (1, len(LABELS)) or output_info["dtype"] != np.float32:
        raise ValueError("Unexpected legacy TFLite output signature")

    def predict(image: np.ndarray) -> np.ndarray:
        interpreter.set_tensor(input_info["index"], image.reshape(expected_shape))
        interpreter.invoke()
        return interpreter.get_tensor(output_info["index"])[0]

    return predict


def check_parity(model: nn.Module, predict, images: np.ndarray, erase_threshold: float | None) -> float:
    with torch.inference_mode():
        expected = model(torch.from_numpy(images[:, None])).numpy()
    actual = np.stack([predict(image) for image in images])
    np.testing.assert_allclose(actual, expected, rtol=0, atol=PARITY_TOLERANCE)
    np.testing.assert_array_equal(
        candidate_actions(actual, erase_threshold),
        candidate_actions(expected, erase_threshold),
    )
    if not np.isfinite(actual).all() or np.any((actual < 0) | (actual > 1)):
        raise ValueError("ONNX output must contain finite scores in [0, 1]")
    return float(np.max(np.abs(actual - expected)))


def setup_training():
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is unavailable. Install the CUDA 12.8 wheels and check the NVIDIA driver.")
    if torch.version.cuda != "12.8":
        raise SystemExit(f"Expected the PyTorch CUDA 12.8 build, found {torch.version.cuda}.")
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)


def train_experiment(name: str, train: Samples, validation: Samples, config: TrainingConfig):
    setup_training()
    print(f"Training {name} on {torch.cuda.get_device_name()}", flush=True)
    return train_model(train, validation, config)


def select_model(models: dict[str, nn.Module], validation: Samples):
    images = image_tensor(validation)
    with torch.inference_mode():
        scores = {
            name: torch.cat([model(batch) for batch in images.split(256)]).numpy()
            for name, model in models.items()
        }
    subsets = [subset for count in range(1, len(models) + 1) for subset in combinations(models, count)]
    ranks = {
        subset: validation_rank(np.mean([scores[name] for name in subset], axis=0), validation)
        for subset in subsets
    }
    best = max(subsets, key=lambda subset: (ranks[subset], -len(subset)))
    for subset, rank in ranks.items():
        print(f"{' + '.join(subset)}: validation digits {rank[1]:.2%}, minimum erase recall {rank[2]:.2%}", flush=True)
    selected = models[best[0]] if len(best) == 1 else Ensemble([models[name] for name in best]).eval()
    summary = [
        {"members": list(subset), "digit_accuracy": rank[1], "minimum_erase_recall": rank[2]}
        for subset, rank in ranks.items()
    ]
    return selected, list(best), summary


def run(smoke: bool, output: Path, experiments: int):
    setup_training()

    train, validation, test = load_samples(ROOT / "data", SEED, smoke)
    configs = dict(list(EXPERIMENTS.items())[:experiments])
    if smoke:
        configs = {name: replace(config, epochs=1) for name, config in configs.items()}
    if experiments == 1:
        name, config = next(iter(configs.items()))
        models = {name: train_experiment(name, train, validation, config)}
    else:
        with ProcessPoolExecutor(max_workers=experiments) as pool:
            jobs = {
                name: pool.submit(train_experiment, name, train, validation, config)
                for name, config in configs.items()
            }
            models = {name: job.result() for name, job in jobs.items()}
    model, selected, experiment_results = select_model(models, validation)
    print(f"Selected on validation: {' + '.join(selected)}", flush=True)
    output.mkdir(parents=True, exist_ok=True)
    candidate_path = output / "candidate.onnx"
    predict = export_model(model, candidate_path)
    validation_images = validation.images.astype(np.float32) / 255
    parity_indices = np.linspace(0, len(validation_images) - 1, 64, dtype=int)
    validation_scores = np.stack([predict(image) for image in validation_images])
    erase_threshold = calibrate_erase_threshold(validation_scores, validation.labels)
    parity_error = check_parity(model, predict, validation_images[parity_indices], erase_threshold)
    validation_metrics = summarize(validation, candidate_actions(validation_scores, erase_threshold))
    if validation_metrics["false_erases"]["count"] != 0:
        raise RuntimeError("Calibrated threshold allows a false erase on the validation set")

    test_images = test.images.astype(np.float32) / 255
    candidate_scores, candidate_latency = measure_inference(predict, test_images)
    baseline_scores, baseline_latency = measure_inference(legacy_predictor(), test_images)
    metrics = {
        "mode": "smoke" if smoke else "full",
        "seed": SEED,
        "training": {
            "gpu": torch.cuda.get_device_name(),
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "experiments": {name: asdict(config) for name, config in configs.items()},
            "validation_comparison": experiment_results,
            "selected": selected,
            "train_samples": len(train.labels),
            "validation_samples": len(validation.labels),
            "test_samples": len(test.labels),
        },
        "onnx": {
            "opset": OPSET,
            "runtime_version": ort.__version__,
            "max_absolute_parity_error": parity_error,
            "digit_threshold": DIGIT_THRESHOLD,
            "erase_threshold": erase_threshold,
            "validation": validation_metrics,
            "test": summarize(test, candidate_actions(candidate_scores, erase_threshold)),
            "size_bytes": candidate_path.stat().st_size,
            "latency": candidate_latency,
        },
        "legacy_tflite": {
            "test": summarize(test, legacy_actions(baseline_scores)),
            "size_bytes": LEGACY_MODEL.stat().st_size,
            "latency": baseline_latency,
        },
    }
    config = {
        "opset": OPSET,
        "input": {"name": "image", "dtype": "float32", "shape": ONNX_INPUT_SHAPE},
        "output": {"name": "scores", "dtype": "float32", "shape": (1, len(LABELS)), "labels": LABELS},
        "thresholds": {label: DIGIT_THRESHOLD for label in LABELS[:-1]} | {"ERASE": erase_threshold},
    }
    for filename, content in (("candidate.json", config), ("metrics.json", metrics)):
        (output / filename).write_text(json.dumps(content, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Saved ONNX model, configuration, and metrics in {output.resolve()}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Train Sudoku Ink recognition on CUDA and compare against TFLite.")
    parser.add_argument("--smoke", action="store_true", help="Exercise the full pipeline with a small sample and one epoch.")
    parser.add_argument("--output", type=Path, help="Override the local artifact directory.")
    parser.add_argument("--experiments", type=int, choices=(1, 2, 3), default=1, help="Number of concurrent CUDA experiments.")
    arguments = parser.parse_args()
    default_output = ROOT / "out" / ("smoke" if arguments.smoke else "full")
    run(arguments.smoke, arguments.output or default_output, arguments.experiments)


if __name__ == "__main__":
    main()
