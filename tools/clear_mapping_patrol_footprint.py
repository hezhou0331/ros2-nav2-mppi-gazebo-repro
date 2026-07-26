#!/usr/bin/python3
"""Clear the robot footprint along the verified mapping patrol trajectory."""

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml


DEFAULT_CLEARANCE_RADIUS_M = 0.65
PATROL_ROUTE = (
    (-5.8, 0.0),
    (-4.9, 0.0),
    (-4.9, -1.2),
    (3.3, -1.2),
    (3.3, 1.2),
    (-4.9, 1.2),
    (-4.9, 0.0),
)


def next_pgm_token(data, offset):
    while offset < len(data):
        if data[offset] == ord("#"):
            newline = data.find(b"\n", offset)
            if newline < 0:
                raise ValueError("PGM comment is not terminated")
            offset = newline + 1
        elif chr(data[offset]).isspace():
            offset += 1
        else:
            break
    start = offset
    while offset < len(data) and not chr(data[offset]).isspace():
        offset += 1
    if start == offset:
        raise ValueError("PGM header is incomplete")
    return data[start:offset].decode("ascii"), offset


def read_pgm(path):
    data = path.read_bytes()
    offset = 0
    tokens = []
    for _ in range(4):
        token, offset = next_pgm_token(data, offset)
        tokens.append(token)
    if tokens[0] != "P5":
        raise ValueError(f"expected binary PGM P5, got {tokens[0]!r}")
    width, height, maximum = map(int, tokens[1:])
    if maximum != 255:
        raise ValueError(f"expected 8-bit PGM, got maximum {maximum}")
    if data[offset:offset + 2] == b"\r\n":
        offset += 2
    elif offset < len(data) and chr(data[offset]).isspace():
        offset += 1
    else:
        raise ValueError("PGM header has no pixel separator")
    pixels = bytearray(data[offset:])
    if len(pixels) != width * height:
        raise ValueError(
            f"PGM pixel count mismatch: expected {width * height}, got {len(pixels)}"
        )
    return width, height, pixels


def point_segment_distance(px, py, x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    squared_length = dx * dx + dy * dy
    if squared_length == 0.0:
        return math.hypot(px - x1, py - y1)
    fraction = ((px - x1) * dx + (py - y1) * dy) / squared_length
    fraction = max(0.0, min(1.0, fraction))
    nearest_x = x1 + fraction * dx
    nearest_y = y1 + fraction * dy
    return math.hypot(px - nearest_x, py - nearest_y)


def clear_route(pixels, width, height, origin_x, origin_y, resolution, radius):
    changed = {"occupied": 0, "unknown": 0, "other": 0}
    for row in range(height):
        world_y = origin_y + (height - 1 - row + 0.5) * resolution
        for column in range(width):
            world_x = origin_x + (column + 0.5) * resolution
            swept = any(
                point_segment_distance(world_x, world_y, *start, *finish) <= radius
                for start, finish in zip(PATROL_ROUTE, PATROL_ROUTE[1:])
            )
            if not swept:
                continue
            index = row * width + column
            value = pixels[index]
            if value == 254:
                continue
            if value == 0:
                changed["occupied"] += 1
            elif value == 205:
                changed["unknown"] += 1
            else:
                changed["other"] += 1
            pixels[index] = 254
    return changed


def atomic_write(path, data):
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def write_json(path, payload):
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def positive_float(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", required=True, type=Path, help="Saved map YAML path")
    parser.add_argument("--output", required=True, type=Path, help="Cleanup JSON report")
    parser.add_argument(
        "--radius", type=positive_float, default=DEFAULT_CLEARANCE_RADIUS_M
    )
    args = parser.parse_args()

    metadata = yaml.safe_load(args.map.read_text(encoding="utf-8"))
    image = Path(metadata["image"])
    if not image.is_absolute():
        image = args.map.parent / image
    image = image.resolve()
    resolution = float(metadata["resolution"])
    origin = metadata["origin"]
    if not isinstance(origin, list) or len(origin) < 2:
        raise SystemExit(f"Map has invalid origin: {args.map}")

    width, height, pixels = read_pgm(image)
    changed = clear_route(
        pixels,
        width,
        height,
        float(origin[0]),
        float(origin[1]),
        resolution,
        args.radius,
    )
    header = (
        "P5\n"
        "# Cleared only along the verified ATEC mapping patrol footprint\n"
        f"{width} {height}\n255\n"
    ).encode("ascii")
    atomic_write(image, header + pixels)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "success": True,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "map_yaml": str(args.map.resolve()),
        "map_image": str(image),
        "width": width,
        "height": height,
        "resolution_m": resolution,
        "clearance_radius_m": args.radius,
        "route": [{"x": x, "y": y} for x, y in PATROL_ROUTE],
        "changed_pixels": changed,
        "changed_pixels_total": sum(changed.values()),
    }
    write_json(args.output, report)
    print(
        f"Cleared {report['changed_pixels_total']} patrol-footprint pixels in {image}; "
        f"report written to {args.output}"
    )


if __name__ == "__main__":
    main()
