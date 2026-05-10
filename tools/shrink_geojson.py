#!/usr/bin/env python3
"""Shrink GeoJSON polygon complexity with lossy simplification.

Usage:
  python3 shrink_geojson.py INPUT.geojson FACTOR

The output is written next to INPUT as:
  <INPUT_STEM>_shrinked.geojson

FACTOR controls reduction strength:
- 1.0  -> mild simplification
- 2.0+ -> stronger simplification
- 5.0+ -> aggressive simplification
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

Point = Tuple[float, float]
Ring = List[Point]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reduce polygon point count in a GeoJSON file."
    )
    parser.add_argument("input_file", help="Path to input .geojson file")
    parser.add_argument(
        "factor",
        type=float,
        help="Reduction factor (>0). Higher means stronger simplification.",
    )
    return parser.parse_args()


def _as_point(value) -> Point:
    return (float(value[0]), float(value[1]))


def _ensure_closed(ring: Ring) -> Ring:
    if not ring:
        return []
    if ring[0] != ring[-1]:
        return ring + [ring[0]]
    return ring


def _perp_distance(point: Point, start: Point, end: Point) -> float:
    sx, sy = start
    ex, ey = end
    px, py = point

    dx = ex - sx
    dy = ey - sy
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - sx, py - sy)

    return abs(dy * px - dx * py + ex * sy - ey * sx) / math.hypot(dx, dy)


def _rdp(points: Sequence[Point], epsilon: float) -> List[Point]:
    if len(points) <= 2:
        return list(points)

    start = points[0]
    end = points[-1]
    max_dist = -1.0
    index = -1

    for i in range(1, len(points) - 1):
        dist = _perp_distance(points[i], start, end)
        if dist > max_dist:
            max_dist = dist
            index = i

    if max_dist > epsilon and index != -1:
        left = _rdp(points[: index + 1], epsilon)
        right = _rdp(points[index:], epsilon)
        return left[:-1] + right

    return [start, end]


def _ring_bbox_diag(ring: Ring) -> float:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys))


def simplify_ring(ring_raw: Iterable[Iterable[float]], factor: float) -> List[List[float]]:
    ring: Ring = [_as_point(p) for p in ring_raw]
    ring = _ensure_closed(ring)
    if len(ring) < 5:
        return [[x, y] for x, y in ring]

    core = ring[:-1]

    # Coarse pre-sampling can significantly reduce size for very dense rings.
    step = max(1, int(factor // 2))
    if step > 1 and len(core) > 80:
        sampled = core[::step]
        if sampled[-1] != core[-1]:
            sampled.append(core[-1])
        core = sampled

    bbox_diag = _ring_bbox_diag(core)
    epsilon = bbox_diag * 0.0002 * factor
    simplified = _rdp(core, epsilon)

    if len(simplified) < 3:
        simplified = core[:3]

    closed = _ensure_closed(simplified)
    if len(closed) < 4:
        closed = _ensure_closed(core)

    return [[x, y] for x, y in closed]


def simplify_geometry(geometry: dict, factor: float) -> dict:
    if not geometry:
        return geometry

    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if coords is None:
        return geometry

    if gtype == "Polygon":
        new_coords = [simplify_ring(ring, factor) for ring in coords]
        return {**geometry, "coordinates": new_coords}

    if gtype == "MultiPolygon":
        new_coords = [
            [simplify_ring(ring, factor) for ring in polygon]
            for polygon in coords
        ]
        return {**geometry, "coordinates": new_coords}

    return geometry


def count_points_in_geometry(geometry: dict) -> int:
    if not geometry:
        return 0

    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if coords is None:
        return 0

    if gtype == "Polygon":
        return sum(len(ring) for ring in coords)

    if gtype == "MultiPolygon":
        return sum(len(ring) for polygon in coords for ring in polygon)

    return 0


def output_path_for(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_shrinked.geojson")


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_file)

    if args.factor <= 0:
        raise SystemExit("Factor must be > 0.")

    if not input_path.is_file():
        raise SystemExit(f"Input file not found: {input_path}")

    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features")
    if not isinstance(features, list):
        raise SystemExit("Input is not a valid GeoJSON FeatureCollection.")

    points_before = 0
    points_after = 0

    new_features = []
    for feature in features:
        geometry = feature.get("geometry")
        points_before += count_points_in_geometry(geometry)
        new_geometry = simplify_geometry(geometry, args.factor)
        points_after += count_points_in_geometry(new_geometry)
        new_features.append({**feature, "geometry": new_geometry})

    out_data = {**data, "features": new_features}
    out_path = output_path_for(input_path)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, separators=(",", ":"))

    in_size = input_path.stat().st_size
    out_size = out_path.stat().st_size

    print(f"Input:  {input_path}")
    print(f"Output: {out_path}")
    print(f"Points: {points_before} -> {points_after}")
    if points_before > 0:
        print(f"Point reduction: {100.0 * (1.0 - points_after / points_before):.2f}%")
    print(f"Size:   {in_size} -> {out_size} bytes")
    if in_size > 0:
        print(f"Size reduction:  {100.0 * (1.0 - out_size / in_size):.2f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())