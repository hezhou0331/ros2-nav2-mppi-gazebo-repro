#!/usr/bin/env python3
"""Render concise, traceable GitHub showcase media from real run artifacts.

This tool deliberately separates presentation rendering from robot control.  It
only crops, annotates, and time-compresses already-recorded simulation output;
it never changes a Nav2 or platform velocity parameter.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Iterable
import zlib


CANVAS_WIDTH = 1600
CANVAS_HEIGHT = 900
BACKGROUND = "#07111f"
PANEL = "#0d1b2d"
MUTED = "#91a4bd"
ACCENT = "#39d5ff"
SUCCESS = "#6ee7b7"
FONT_FAMILY = "Noto Sans CJK SC, Noto Sans, sans-serif"


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


def draw_text(text: str, x: int, y: int, size: int, color: str, *, weight: str = "") -> str:
    """Return a drawtext filter fragment for a fixed local font."""
    del weight  # Noto's regular TTC is installed on the supported rendering host.
    # Keep filter syntax simple and portable: the visual copy uses an em dash
    # instead of a literal colon, which otherwise needs fragile FFmpeg escaping.
    escaped = text.replace("'", r"\\'").replace(":", " —")
    return (
        f"drawtext=fontfile={FONT}:text='{escaped}':x={x}:y={y}:"
        f"fontsize={size}:fontcolor={color}"
    )


def pgm_token_reader(data: bytes):
    position = 0

    def read_token() -> bytes:
        nonlocal position
        while position < len(data):
            if data[position] in b" \t\r\n":
                position += 1
            elif data[position] == ord("#"):
                while position < len(data) and data[position] not in b"\r\n":
                    position += 1
            else:
                break
        start = position
        while position < len(data) and data[position] not in b" \t\r\n":
            position += 1
        return data[start:position]

    return read_token, lambda: position


def read_pgm(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    read_token, get_position = pgm_token_reader(data)
    magic = read_token()
    if magic != b"P5":
        raise ValueError(f"Only binary P5 PGM maps are supported: {path}")
    width = int(read_token())
    height = int(read_token())
    maximum = int(read_token())
    if maximum != 255:
        raise ValueError(f"Expected an 8-bit PGM map, got maximum={maximum}: {path}")
    position = get_position()
    while position < len(data) and data[position] in b" \t\r\n":
        position += 1
    pixels = data[position:]
    if len(pixels) != width * height:
        raise ValueError(f"Invalid PGM payload length in {path}")
    return width, height, pixels


def write_png_rgb(path: Path, width: int, height: int, pixels: bytes) -> None:
    if len(pixels) != width * height * 3:
        raise ValueError("RGB image byte length does not match dimensions")
    scanlines = b"".join(
        b"\x00" + pixels[row * width * 3:(row + 1) * width * 3]
        for row in range(height)
    )
    payload = b"\x89PNG\r\n\x1a\n"

    def chunk(kind: bytes, content: bytes) -> bytes:
        return (
            len(content).to_bytes(4, "big")
            + kind
            + content
            + (zlib.crc32(kind + content) & 0xFFFFFFFF).to_bytes(4, "big")
        )

    payload += chunk(b"IHDR", width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00")
    payload += chunk(b"IDAT", zlib.compress(scanlines, level=9))
    payload += chunk(b"IEND", b"")
    path.write_bytes(payload)


def set_rgb(pixels: bytearray, width: int, height: int, x: int, y: int, color: tuple[int, int, int]) -> None:
    if not (0 <= x < width and 0 <= y < height):
        return
    offset = (y * width + x) * 3
    pixels[offset:offset + 3] = bytes(color)


def draw_disc(pixels: bytearray, width: int, height: int, x: int, y: int, radius: int, color: tuple[int, int, int]) -> None:
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                set_rgb(pixels, width, height, x + dx, y + dy, color)


def draw_line(pixels: bytearray, width: int, height: int, start: tuple[int, int], end: tuple[int, int], color: tuple[int, int, int]) -> None:
    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    step_x = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    step_y = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        draw_disc(pixels, width, height, x0, y0, 2, color)
        if x0 == x1 and y0 == y1:
            break
        twice_error = 2 * error
        if twice_error >= dy:
            error += dy
            x0 += step_x
        if twice_error <= dx:
            error += dx
            y0 += step_y


def parse_map_metadata(path: Path) -> tuple[float, float, float]:
    text = path.read_text(encoding="utf-8")
    resolution_match = re.search(r"^resolution:\s*([0-9.eE+-]+)", text, re.MULTILINE)
    origin_match = re.search(
        r"^origin:\s*\[\s*([0-9.eE+-]+)\s*,\s*([0-9.eE+-]+)",
        text,
        re.MULTILINE,
    )
    if not resolution_match or not origin_match:
        raise ValueError(f"Could not read resolution/origin from {path}")
    return float(resolution_match.group(1)), float(origin_match.group(1)), float(origin_match.group(2))


def map_crop_and_colorize(
    pgm: Path,
    map_yaml: Path,
    mapping_report: Path,
    output: Path,
) -> dict[str, object]:
    width, height, pixels = read_pgm(pgm)
    resolution, origin_x, origin_y = parse_map_metadata(map_yaml)
    report = json.loads(mapping_report.read_text(encoding="utf-8"))
    routes = report.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError(f"Mapping patrol report contains no routes: {mapping_report}")
    completed_waypoints = report.get("waypoints_completed")
    waypoint_results = report.get("waypoint_results")
    patrol_succeeded = (
        report.get("success") is True
        and completed_waypoints == len(routes)
        and isinstance(waypoint_results, list)
        and len(waypoint_results) == len(routes)
        and all(
            isinstance(result, dict) and result.get("status") == "SUCCEEDED"
            for result in waypoint_results
        )
    )
    if not patrol_succeeded:
        raise ValueError(
            "GitHub mapping showcase requires a fully successful patrol report "
            f"({completed_waypoints}/{len(routes)} completed): {mapping_report}"
        )

    known = [(index % width, index // width) for index, value in enumerate(pixels) if value != 205]
    if not known:
        raise ValueError(f"No known cells in {pgm}")

    def to_pixel(x: float, y: float) -> tuple[int, int]:
        return (
            round((x - origin_x) / resolution),
            round(height - (y - origin_y) / resolution),
        )

    route_pixels = [to_pixel(float(route["x"]), float(route["y"])) for route in routes]
    all_x = [point[0] for point in known] + [point[0] for point in route_pixels]
    all_y = [point[1] for point in known] + [point[1] for point in route_pixels]
    pad = 18
    left = max(0, min(all_x) - pad)
    right = min(width, max(all_x) + pad + 1)
    top = max(0, min(all_y) - pad)
    bottom = min(height, max(all_y) + pad + 1)
    crop_width = right - left
    crop_height = bottom - top

    colored = bytearray(crop_width * crop_height * 3)
    occupied = free = unknown = 0
    palette = {
        0: (251, 113, 133),   # occupied
        205: (37, 55, 78),   # unknown
        254: (224, 238, 245),  # free
    }
    for y in range(crop_height):
        for x in range(crop_width):
            source = pixels[(top + y) * width + left + x]
            if source == 0:
                occupied += 1
            elif source == 254:
                free += 1
            else:
                unknown += 1
            color = palette.get(source, palette[205])
            target = (y * crop_width + x) * 3
            colored[target:target + 3] = bytes(color)
    cropped_route_pixels = [
        (x - left, y - top)
        for x, y in route_pixels
    ]
    for start, end in zip(cropped_route_pixels, cropped_route_pixels[1:]):
        draw_line(colored, crop_width, crop_height, start, end, (53, 213, 255))
    for point in cropped_route_pixels:
        draw_disc(colored, crop_width, crop_height, point[0], point[1], 6, (110, 231, 183))
        draw_disc(colored, crop_width, crop_height, point[0], point[1], 3, (7, 17, 31))
    write_png_rgb(output, crop_width, crop_height, bytes(colored))
    return {
        "width": width,
        "height": height,
        "resolution": resolution,
        "origin_x": origin_x,
        "origin_y": origin_y,
        "left": left,
        "top": top,
        "crop_width": crop_width,
        "crop_height": crop_height,
        "routes": routes,
        "route_pixels": route_pixels,
        "patrol_succeeded": patrol_succeeded,
        "completed_waypoints": completed_waypoints,
        "unique_route_locations": len(set(route_pixels)),
        "occupied": occupied,
        "free": free,
        "unknown": unknown,
    }


def render_lidar_card(source: Path, output: Path, work_dir: Path) -> None:
    del work_dir
    filters = [
        f"color=c=0x07111f:s={CANVAS_WIDTH}x{CANVAS_HEIGHT}:d=1[background]",
        "[0:v]crop=iw*0.744:ih*0.893:iw*0.228:ih*0.098,scale=1380:540:flags=lanczos[lidar]",
        "[background]drawbox=x=70:y=224:w=1460:h=590:color=0x0D1B2D:t=fill,drawbox=x=70:y=224:w=1460:h=590:color=0x1D3955:t=2[panel]",
        "[panel][lidar]overlay=x=110:y=245[content]",
        "[content]"
        + ",".join([
            draw_text("01 · MAPPING", 72, 54, 24, "0x39D5FF"),
            draw_text("Live 3D LiDAR point cloud", 72, 102, 46, "0xF8FBFF"),
            draw_text("A2 head sensor · 720 × 16 beams · 10 Hz · cyan: PointCloud2 · yellow: navigation scan", 72, 162, 22, "0x91A4BD"),
            "drawbox=x=104:y=746:w=370:h=42:color=0x12354B:t=fill",
            "drawbox=x=122:y=759:w=14:h=14:color=0x39D5FF:t=fill",
            draw_text("RAW 3D SENSOR FRAME", 152, 756, 18, "0xE5F6FF"),
            "drawbox=x=72:y=838:w=1456:h=1:color=0x23445F:t=fill",
            draw_text("Presentation note: live 3D sensor observation — not a reconstructed 3D SLAM map.", 72, 852, 18, "0x91A4BD"),
        ])
        + "[out]",
    ]
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-filter_complex", ";".join(filters), "-map", "[out]", "-frames:v", "1", str(output),
    ])


def render_grid_card(
    pgm: Path,
    map_yaml: Path,
    mapping_report: Path,
    cleanup_report: Path,
    output: Path,
    work_dir: Path,
) -> dict[str, object]:
    colorized = work_dir / "occupancy_colorized.png"
    metadata = map_crop_and_colorize(pgm, map_yaml, mapping_report, colorized)
    cleanup = json.loads(cleanup_report.read_text(encoding="utf-8"))
    changed_pixels = cleanup.get("changed_pixels")
    if not isinstance(changed_pixels, dict):
        raise ValueError(f"Invalid footprint-cleanup report: {cleanup_report}")
    changed_total = sum(int(value) for value in changed_pixels.values())
    cleanup_valid = (
        cleanup.get("success") is True
        and cleanup.get("width") == metadata["width"]
        and cleanup.get("height") == metadata["height"]
        and abs(float(cleanup.get("resolution_m", 0.0)) - float(metadata["resolution"])) < 1e-9
        and cleanup.get("changed_pixels_total") == changed_total
    )
    if not cleanup_valid:
        raise ValueError(
            "Footprint-cleanup report does not match the rendered navigation grid: "
            f"{cleanup_report}"
        )
    clearance_radius = float(cleanup["clearance_radius_m"])
    metadata["cleanup"] = {
        "success": True,
        "clearance_radius_m": clearance_radius,
        "changed_pixels": changed_pixels,
        "changed_pixels_total": changed_total,
    }
    route_count = len(metadata["routes"])
    completed_waypoints = int(metadata["completed_waypoints"])
    unique_locations = int(metadata["unique_route_locations"])
    known = int(metadata["occupied"]) + int(metadata["free"])
    filters = [
        f"color=c=0x07111f:s={CANVAS_WIDTH}x{CANVAS_HEIGHT}:d=1[background]",
        "[0:v]scale=1040:548:flags=neighbor[map]",
        "[background]drawbox=x=70:y=218:w=1150:h=590:color=0x0D1B2D:t=fill,drawbox=x=70:y=218:w=1150:h=590:color=0x1D3955:t=2,drawbox=x=1252:y=218:w=278:h=590:color=0x0D1B2D:t=fill,drawbox=x=1252:y=218:w=278:h=590:color=0x1D3955:t=2[panels]",
        "[panels][map]overlay=x=124:y=239[content]",
        "[content]"
        + ",".join([
            draw_text("01 · MAPPING", 72, 54, 24, "0x6EE7B7"),
            draw_text("Validated 2D navigation grid", 72, 102, 46, "0xF8FBFF"),
            draw_text(
                f"saved SLAM map · verified {clearance_radius:.2f} m patrol-footprint cleanup "
                "· cyan: commanded route",
                72,
                162,
                22,
                "0x91A4BD",
            ),
            draw_text("MAP STATUS", 1284, 244, 24, "0xF8FBFF"),
            draw_text(f"{completed_waypoints}/{route_count}", 1284, 292, 42, "0x6EE7B7"),
            draw_text("patrol checks", 1284, 344, 18, "0x91A4BD"),
            draw_text(f"{unique_locations} unique map locations", 1284, 370, 15, "0x91A4BD"),
            draw_text(f"{float(metadata['resolution']):.02f} m", 1284, 400, 32, "0xF8FBFF"),
            draw_text("grid resolution", 1284, 442, 18, "0x91A4BD"),
            draw_text(f"{known:,}", 1284, 498, 28, "0xF8FBFF"),
            draw_text("known cells", 1284, 538, 18, "0x91A4BD"),
            "drawbox=x=1284:y=614:w=16:h=16:color=0x35D5FF:t=fill",
            draw_text("patrol route", 1312, 610, 18, "0xD8E7F2"),
            "drawbox=x=1284:y=660:w=16:h=16:color=0xFB7185:t=fill",
            draw_text("occupied", 1312, 656, 18, "0xD8E7F2"),
            "drawbox=x=1284:y=706:w=16:h=16:color=0xE0EEF5:t=fill",
            draw_text("free space", 1312, 702, 18, "0xD8E7F2"),
            draw_text(
                f"Validated post-process: {changed_total:,} cells cleared only inside the "
                f"{clearance_radius:.2f} m patrol footprint; cyan is commanded route, not odometry.",
                72,
                852,
                18,
                "0x91A4BD",
            ),
        ])
        + "[out]",
    ]
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(colorized),
        "-filter_complex", ";".join(filters), "-map", "[out]", "-frames:v", "1", str(output),
    ])
    return metadata


def render_navigation_assets(source: Path, png: Path, mp4: Path, gif: Path, speed: float) -> None:
    if speed <= 1.0:
        raise ValueError("--navigation-speed must be greater than 1.0")
    def composition(setpts: str = "") -> str:
        left_prefix = f"{setpts}," if setpts else ""
        return ";".join([
            f"[0:v]{left_prefix}split=2[gazebo_source][rviz_source]",
            "[gazebo_source]crop=450:720:0:150,scale=480:580:flags=lanczos[gazebo]",
            "[rviz_source]crop=500:333:1410:390,scale=900:580:flags=lanczos[rviz]",
            f"color=c=0x07111f:s={CANVAS_WIDTH}x{CANVAS_HEIGHT}:d=1[background]",
            "[background]drawbox=x=70:y=180:w=520:h=600:color=0x0D1B2D:t=fill,drawbox=x=70:y=180:w=520:h=600:color=0x1D3955:t=2,drawbox=x=610:y=180:w=920:h=600:color=0x0D1B2D:t=fill,drawbox=x=610:y=180:w=920:h=600:color=0x1D3955:t=2[cards]",
            "[cards][gazebo]overlay=x=90:y=190[with_gazebo]",
            "[with_gazebo][rviz]overlay=x=620:y=190[content]",
            "[content]"
            + ",".join([
                draw_text("02 · NAVIGATION", 72, 48, 24, "0x39D5FF"),
                draw_text("Dual-goal obstacle avoidance", 72, 88, 46, "0xF8FBFF"),
                draw_text(f"{speed:g}x playback — simulation visualization — original control limits unchanged", 72, 140, 20, "0x91A4BD"),
                draw_text("GAZEBO SIMULATION", 90, 806, 18, "0x39D5FF"),
                draw_text("NAV2 GLOBAL + LOCAL COSTMAP", 620, 806, 18, "0x6EE7B7"),
                draw_text("Goal 1 + Goal 2 are shown as an accelerated replay; no controller speed was raised.", 72, 850, 18, "0x91A4BD"),
            ])
            + "[out]",
        ])

    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "25", "-i", str(source),
        "-filter_complex", composition(), "-map", "[out]", "-frames:v", "1", str(png),
    ])
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-filter_complex", composition(f"setpts=PTS/{speed:g}"), "-map", "[out]", "-an", "-r", "12",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4),
    ])
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp4),
        "-filter_complex", "[0:v]fps=8,scale=900:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=3",
        "-loop", "0", str(gif),
    ])


def relative(path: Path, repository: Path) -> str:
    try:
        return str(path.resolve().relative_to(repository.resolve()))
    except ValueError:
        return str(path.resolve())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--lidar-3d-source", type=Path, required=True, help="Raw RViz screenshot from a live simulation run.")
    parser.add_argument("--map-pgm", type=Path, required=True)
    parser.add_argument("--map-yaml", type=Path, required=True)
    parser.add_argument("--mapping-report", type=Path, required=True)
    parser.add_argument(
        "--map-cleanup-report",
        type=Path,
        required=True,
        help="Recorded report for the patrol-footprint cleanup applied to the saved navigation map.",
    )
    parser.add_argument("--navigation-source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/media"))
    parser.add_argument("--manifest", type=Path, default=Path("docs/evidence/github_showcase_media_manifest.json"))
    parser.add_argument("--navigation-speed", type=float, default=5.0)
    args = parser.parse_args()

    repository = args.repository.resolve()
    output_dir = (repository / args.output_dir).resolve() if not args.output_dir.is_absolute() else args.output_dir.resolve()
    manifest_path = (repository / args.manifest).resolve() if not args.manifest.is_absolute() else args.manifest.resolve()
    for path in (
        args.lidar_3d_source,
        args.map_pgm,
        args.map_yaml,
        args.mapping_report,
        args.map_cleanup_report,
        args.navigation_source,
    ):
        if not path.is_file():
            parser.error(f"Required input does not exist: {path}")
    if not shutil.which("ffmpeg"):
        parser.error("ffmpeg is required to render showcase media")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    lidar_output = output_dir / "atec_a2_p7_mapping_lidar_3d.png"
    grid_output = output_dir / "atec_a2_p7_mapping_grid_2d.png"
    navigation_png = output_dir / "atec_a2_p7_navigation_showcase.png"
    navigation_mp4 = output_dir / "atec_a2_p7_navigation_showcase.mp4"
    navigation_gif = output_dir / "atec_a2_p7_navigation_showcase.gif"

    with tempfile.TemporaryDirectory(prefix="atec_showcase_media_") as temporary:
        work_dir = Path(temporary)
        render_lidar_card(args.lidar_3d_source, lidar_output, work_dir)
        grid_metadata = render_grid_card(
            args.map_pgm,
            args.map_yaml,
            args.mapping_report,
            args.map_cleanup_report,
            grid_output,
            work_dir,
        )
        render_navigation_assets(args.navigation_source, navigation_png, navigation_mp4, navigation_gif, args.navigation_speed)

    inputs = {
        "lidar_3d_source": args.lidar_3d_source,
        "map_pgm": args.map_pgm,
        "map_yaml": args.map_yaml,
        "mapping_report": args.mapping_report,
        "map_cleanup_report": args.map_cleanup_report,
        "navigation_source": args.navigation_source,
    }
    outputs = [lidar_output, grid_output, navigation_png, navigation_mp4, navigation_gif]
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "generator": relative(Path(__file__), repository),
        "scope": "GitHub presentation media generated from real simulation artifacts only",
        "claims": {
            "mapping_lidar_3d": "Live RViz PointCloud2 observation, not a reconstructed 3D SLAM map.",
            "mapping_grid_2d": (
                "Navigation grid saved from slam_toolbox /map and then processed by the recorded "
                f"{float(grid_metadata['cleanup']['clearance_radius_m']):.2f} m verified "
                "patrol-footprint cleanup; cyan is the commanded route, not odometry."
            ),
            "navigation_showcase": f"{args.navigation_speed:g}x playback rendering only; controller and platform limits are unchanged.",
        },
        "inputs": {
            name: {"path": relative(path, repository), "sha256": sha256(path)}
            for name, path in inputs.items()
        },
        "mapping_grid": {
            "resolution_m": grid_metadata["resolution"],
            "source_dimensions": [grid_metadata["width"], grid_metadata["height"]],
            "crop_dimensions": [grid_metadata["crop_width"], grid_metadata["crop_height"]],
            "patrol_waypoints": len(grid_metadata["routes"]),
            "patrol_succeeded": grid_metadata["patrol_succeeded"],
            "patrol_waypoints_completed": grid_metadata["completed_waypoints"],
            "patrol_unique_locations": grid_metadata["unique_route_locations"],
            "occupied_cells_in_crop": grid_metadata["occupied"],
            "free_cells_in_crop": grid_metadata["free"],
            "unknown_cells_in_crop": grid_metadata["unknown"],
            "footprint_cleanup": grid_metadata["cleanup"],
        },
        "outputs": [
            {"path": relative(path, repository), "sha256": sha256(path), "size_bytes": path.stat().st_size}
            for path in outputs
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
