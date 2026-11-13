import argparse
import os
import re
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path


PACKAGE = "com.onyx.zhdanov.game.Sudoku"
DIRECTORY = "no_backup/recognition-samples"
SAMPLE_NAME = re.compile(r"([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})--([1-9]|ERASE|unlabeled)\.png")
PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def adb(arguments: list[str]) -> bytes:
    result = subprocess.run(["adb", *arguments], capture_output=True, check=False)
    if result.returncode:
        details = (result.stderr or result.stdout).decode(errors="replace").strip()
        raise RuntimeError(details or f"ADB exited with status {result.returncode}")
    return result.stdout


def verify_png(image: bytes) -> None:
    if not image.startswith(PNG_HEADER):
        raise ValueError("Sample is not a PNG")
    offset = len(PNG_HEADER)
    has_image_data = False
    while offset + 12 <= len(image):
        length, kind = struct.unpack_from(">I4s", image, offset)
        end = offset + 12 + length
        if end > len(image):
            break
        payload = image[offset + 8:end - 4]
        checksum, = struct.unpack_from(">I", image, end - 4)
        if zlib.crc32(kind + payload) != checksum:
            raise ValueError("Sample PNG checksum mismatch")
        if offset == len(PNG_HEADER):
            if kind != b"IHDR" or length != 13 or struct.unpack_from(">II", payload) != (28, 28):
                raise ValueError("Expected a 28×28 PNG")
        has_image_data |= kind == b"IDAT"
        if kind == b"IEND" and length == 0 and has_image_data and end == len(image):
            return
        offset = end
    raise ValueError("Sample PNG is incomplete")


def store_sample(destination: Path, image: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != image:
            raise ValueError(f"Different sample already exists at {destination}")
        return

    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
        pending = Path(temporary.name)
        try:
            temporary.write(image)
            temporary.flush()
            os.fsync(temporary.fileno())
        except OSError:
            temporary.close()
            pending.unlink(missing_ok=True)
            raise
    try:
        os.replace(pending, destination)
    finally:
        pending.unlink(missing_ok=True)


def export_samples(serial: str | None, output: Path, delete: bool) -> int:
    if serial is None:
        serial = adb(["get-serialno"]).decode().strip()
    shell = ["-s", serial, "shell", "-T", "run-as", PACKAGE]
    if "no_backup" not in adb([*shell, "ls", "-1", "."]).decode().splitlines():
        return 0
    files = adb([*shell, "ls", "-1", "no_backup"]).decode().splitlines()
    if DIRECTORY.rsplit("/", 1)[1] not in files:
        return 0

    names = adb([*shell, "ls", "-1", DIRECTORY]).decode().splitlines()
    exported = []
    for name in names:
        match = SAMPLE_NAME.fullmatch(name)
        if match is None:
            continue
        identifier, label = match.groups()
        remote_path = f"{DIRECTORY}/{name}"
        image = adb(["-s", serial, "exec-out", "run-as", PACKAGE, "cat", remote_path])
        verify_png(image)
        store_sample(output / label / f"{identifier}.png", image)
        exported.append(remote_path)

    if delete:
        for start in range(0, len(exported), 50):
            adb([*shell, "rm", "-f", *exported[start:start + 50]])
    return len(exported)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Sudoku Ink recognition samples via ADB.")
    parser.add_argument("--serial", help="ADB serial when multiple devices are connected.")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "data" / "boox")
    parser.add_argument("--delete", action="store_true", help="Remove the exported samples from the device.")
    args = parser.parse_args()
    try:
        count = export_samples(args.serial, args.output, args.delete)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Export failed: {error}", file=sys.stderr)
        return 1
    print(f"Exported {count} samples to {args.output.resolve()}.")
    if args.delete and count:
        print("Removed the exported samples from the device.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
