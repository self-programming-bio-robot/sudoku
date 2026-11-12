from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from torchvision.datasets import MNIST


LABELS = ("1", "2", "3", "4", "5", "6", "7", "8", "9", "ERASE")
IMAGE_SIZE = 28
DRAW_SCALE = 4
CANVAS_SIZE = IMAGE_SIZE * DRAW_SCALE


@dataclass
class Samples:
    images: np.ndarray
    labels: np.ndarray
    kinds: np.ndarray

    def targets(self) -> np.ndarray:
        targets = np.zeros((len(self.labels), len(LABELS)), dtype=np.float32)
        known = self.labels != -1
        targets[np.flatnonzero(known), self.labels[known]] = 1
        return targets


def draw_sample(kind: str, rng: np.random.Generator) -> np.ndarray:
    canvas = Image.new("L", (CANVAS_SIZE, CANVAS_SIZE))
    draw = ImageDraw.Draw(canvas)
    angle = rng.uniform(-0.50, 0.50)
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    center = rng.uniform(48, 64, size=2)
    span = rng.uniform(26, 41, size=2)

    def stroke(points, jitter=0.0):
        points = np.asarray(points)
        points = points + rng.uniform(-jitter, jitter, size=points.shape)
        pixels = np.rint((points * span) @ rotation.T + center).astype(int)
        draw.line(
            [tuple(point) for point in pixels],
            fill=int(rng.integers(205, 256)),
            width=int(rng.integers(4, 13)),
            joint="curve",
        )

    if kind == "cross":
        stroke([(-1, -1), (0, 0), (1, 1)], jitter=0.15)
        stroke([(-1, 1), (0, 0), (1, -1)], jitter=0.15)
    elif kind == "scribble":
        style = rng.choice(("hatch", "zigzag", "scrawl"))
        if style == "hatch":
            for x in np.linspace(-0.8, 0.8, int(rng.integers(3, 7))):
                stroke([(x - 0.18, -0.85), (x + 0.18, 0.85)], jitter=0.15)
        elif style == "zigzag":
            rows = np.linspace(-0.9, 0.9, int(rng.integers(4, 9)))
            stroke([(1 if index % 2 else -1, y) for index, y in enumerate(rows)], jitter=0.19)
        else:
            for _ in range(int(rng.integers(2, 5))):
                middle = rng.uniform(-0.9, 0.9, size=(int(rng.integers(1, 4)), 2))
                ends = rng.uniform(-0.9, 0.9, size=2)
                stroke([(-0.9, ends[0]), *middle, (0.9, ends[1])], jitter=0.12)
    elif kind == "short_stroke":
        x, y = rng.uniform(-0.6, 0.6, size=2)
        length = rng.uniform(0.08, 0.35)
        heading = rng.uniform(0, 2 * np.pi)
        stroke([(x, y), (x + length * np.cos(heading), y + length * np.sin(heading))])
    elif kind == "dot":
        x, y = center + rng.uniform(-24, 24, size=2)
        radius = rng.uniform(2, 6)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
    elif kind != "blank":
        raise ValueError(f"Unexpected synthetic sample kind: {kind}")

    image = canvas.resize((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS)
    return np.asarray(image)


def combine_samples(
    images: np.ndarray,
    digits: np.ndarray,
    positive_count: int,
    negative_count: int,
    seed: int,
) -> Samples:
    rng = np.random.default_rng(seed)
    synthetic_images = []
    labels = [digits - 1]
    kinds = [np.full(len(digits), "digit")]
    for kind, count, label in (
        ("cross", positive_count, LABELS.index("ERASE")),
        ("scribble", positive_count, LABELS.index("ERASE")),
        ("blank", negative_count, -1),
        ("dot", negative_count, -1),
        ("short_stroke", negative_count, -1),
    ):
        synthetic_images.extend(draw_sample(kind, rng) for _ in range(count))
        labels.append(np.full(count, label))
        kinds.append(np.full(count, kind))

    return Samples(
        np.concatenate((images, np.stack(synthetic_images))),
        np.concatenate(labels),
        np.concatenate(kinds),
    )


def load_samples(root: Path, seed: int, smoke: bool) -> tuple[Samples, Samples, Samples]:
    train = MNIST(root=str(root), train=True, download=True)
    test = MNIST(root=str(root), train=False, download=True)
    train_digits = train.targets.numpy()
    test_digits = test.targets.numpy()
    split = np.random.default_rng(seed).permutation(np.flatnonzero(train_digits != 0))
    validation_count = len(split) // 12
    train_indices = split[validation_count:]
    validation_indices = split[:validation_count]
    test_indices = np.flatnonzero(test_digits != 0)
    if smoke:
        train_indices = train_indices[:768]
        validation_indices = validation_indices[:256]
        test_indices = np.random.default_rng(seed).permutation(test_indices)[:256]

    counts = ((64, 24), (32, 12), (32, 12)) if smoke else ((2500, 800), (500, 150), (600, 200))
    train_counts, validation_counts, test_counts = counts
    return (
        combine_samples(train.data.numpy()[train_indices], train_digits[train_indices], *train_counts, seed + 1),
        combine_samples(
            train.data.numpy()[validation_indices], train_digits[validation_indices], *validation_counts, seed + 2
        ),
        combine_samples(test.data.numpy()[test_indices], test_digits[test_indices], *test_counts, seed + 3),
    )
