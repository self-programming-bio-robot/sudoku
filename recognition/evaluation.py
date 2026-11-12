from time import perf_counter_ns

import numpy as np

from data import LABELS, Samples


ERASE = LABELS.index("ERASE")
REJECT = -1
DIGIT_THRESHOLD = 0.5


def candidate_actions(scores: np.ndarray, erase_threshold: float | None) -> np.ndarray:
    winners = scores.argmax(axis=1)
    confidence = scores[np.arange(len(scores)), winners]
    thresholds = np.where(
        winners == ERASE,
        np.inf if erase_threshold is None else erase_threshold,
        DIGIT_THRESHOLD,
    )
    return np.where(confidence > thresholds, winners, REJECT)


def calibrate_erase_threshold(scores: np.ndarray, labels: np.ndarray) -> float | None:
    erase_wins = scores.argmax(axis=1) == ERASE
    false_erase_scores = scores[erase_wins & (labels != ERASE), ERASE]
    # With a strict comparison, the largest false score is the lowest safe threshold.
    threshold = float(false_erase_scores.max(initial=0.0))
    true_erase_scores = scores[erase_wins & (labels == ERASE), ERASE]
    return threshold if np.any(true_erase_scores > threshold) else None


def legacy_actions(scores: np.ndarray) -> np.ndarray:
    winners = scores.argmax(axis=1)
    confidence = scores[np.arange(len(scores)), winners]
    # Kotlin returns 0 both for class 0 and when no class exceeds the threshold.
    return np.where((winners != 0) & (confidence > DIGIT_THRESHOLD), winners - 1, ERASE)


def measure_inference(predict, images: np.ndarray, benchmark_count: int = 200):
    outputs = np.stack([predict(image) for image in images])
    if outputs.shape != (len(images), len(LABELS)) or not np.isfinite(outputs).all():
        raise ValueError("Expected ten finite scores per input")

    benchmark = images[np.linspace(0, len(images) - 1, min(len(images), benchmark_count), dtype=int)]
    for image in benchmark[:20]:
        predict(image)
    durations_ms = []
    for image in benchmark:
        start = perf_counter_ns()
        predict(image)
        durations_ms.append((perf_counter_ns() - start) / 1_000_000)
    return outputs, {
        "samples": len(durations_ms),
        "median_ms": float(np.median(durations_ms)),
        "p95_ms": float(np.percentile(durations_ms, 95)),
        "cpu_threads": 1,
    }


def rate(count: int, total: int) -> dict:
    return {"count": count, "total": total, "rate": count / total if total else None}


def summarize(samples: Samples, actions: np.ndarray) -> dict:
    expected = samples.labels
    digits = samples.kinds == "digit"
    non_erase = expected != ERASE
    correct = actions == expected
    erased = actions == ERASE
    rejected = actions == REJECT
    classes = [*range(len(LABELS)), REJECT]
    return {
        "digit_accuracy": rate(int(np.sum(digits & correct)), int(np.sum(digits))),
        "digit_accuracy_by_class": {
            label: rate(int(np.sum((expected == index) & correct)), int(np.sum(expected == index)))
            for index, label in enumerate(LABELS[:-1])
        },
        "rejections": rate(int(np.sum(rejected)), len(actions)),
        "unrecognized_input_rejections": rate(int(np.sum(rejected & (expected == REJECT))), int(np.sum(expected == REJECT))),
        "erase_recall_by_gesture": {
            kind: rate(int(np.sum(erased & (samples.kinds == kind))), int(np.sum(samples.kinds == kind)))
            for kind in ("cross", "scribble")
        },
        "false_erases": rate(int(np.sum(erased & non_erase)), int(np.sum(non_erase))),
        "false_erases_by_kind": {
            kind: rate(int(np.sum(erased & (samples.kinds == kind))), int(np.sum(samples.kinds == kind)))
            for kind in ("digit", "blank", "dot", "short_stroke")
        },
        "confusion_matrix": {
            "labels": [*LABELS, "REJECT"],
            "rows_expected_columns_predicted": [
                [int(np.sum((expected == truth) & (actions == action))) for action in classes]
                for truth in classes
            ],
        },
    }
