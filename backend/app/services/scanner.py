from dataclasses import dataclass, field
from math import acos, degrees
from typing import Any

import cv2
import numpy as np

from ..config import settings


@dataclass(slots=True)
class DetectionResult:
    corners: np.ndarray | None
    confidence: float
    method: str = "none"
    debug_info: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScanResult:
    color: np.ndarray
    black_and_white: np.ndarray
    detection: DetectionResult


def order_points(points: np.ndarray) -> np.ndarray:
    """Return four points as top-left, top-right, bottom-right, bottom-left."""
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    center = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    clockwise = pts[np.argsort(angles)]
    start = int(np.argmin(clockwise.sum(axis=1)))
    ordered = np.roll(clockwise, -start, axis=0)
    # atan2 ordering is TL, TR, BR, BL in image coordinates. Correct the rare
    # mirrored order defensively by checking the first edge's cross product.
    first_edge = ordered[1] - ordered[0]
    second_edge = ordered[2] - ordered[1]
    cross_product = first_edge[0] * second_edge[1] - first_edge[1] * second_edge[0]
    if cross_product < 0:
        ordered = ordered[[0, 3, 2, 1]]
    return ordered.astype(np.float32)


def _angle_score(points: np.ndarray) -> float:
    pts = order_points(points)
    scores: list[float] = []
    for index in range(4):
        before = pts[(index - 1) % 4] - pts[index]
        after = pts[(index + 1) % 4] - pts[index]
        denominator = float(np.linalg.norm(before) * np.linalg.norm(after))
        if denominator < 1e-6:
            return 0.0
        cosine = float(np.clip(np.dot(before, after) / denominator, -1, 1))
        angle = degrees(acos(cosine))
        scores.append(max(0.0, 1.0 - abs(90.0 - angle) / 55.0))
    return float(np.mean(scores))


def validate_quadrilateral(
    points: np.ndarray,
    image_shape: tuple[int, ...],
    min_area_ratio: float = 0.15,
) -> tuple[bool, dict[str, float | str]]:
    """Apply the same geometry checks to candidates from every detector."""
    try:
        pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    except (TypeError, ValueError):
        return False, {"reason": "candidate does not contain four points"}
    if not np.isfinite(pts).all():
        return False, {"reason": "candidate contains non-finite coordinates"}

    height, width = image_shape[:2]
    margin_x, margin_y = width * 0.08, height * 0.08
    if (
        np.any(pts[:, 0] < -margin_x)
        or np.any(pts[:, 0] > width - 1 + margin_x)
        or np.any(pts[:, 1] < -margin_y)
        or np.any(pts[:, 1] > height - 1 + margin_y)
    ):
        return False, {"reason": "candidate lies outside image bounds"}

    ordered = order_points(pts)
    pairwise = [
        float(np.linalg.norm(ordered[i] - ordered[j]))
        for i in range(4)
        for j in range(i + 1, 4)
    ]
    if min(pairwise) < max(8.0, min(height, width) * 0.025):
        return False, {"reason": "candidate has nearly identical points"}
    if not cv2.isContourConvex(ordered.astype(np.int32)):
        return False, {"reason": "candidate is not convex"}

    area_ratio = abs(float(cv2.contourArea(ordered))) / float(height * width)
    if area_ratio < min_area_ratio:
        return False, {"reason": "candidate area is too small", "area_ratio": round(area_ratio, 4)}

    sides = [float(np.linalg.norm(ordered[(index + 1) % 4] - ordered[index])) for index in range(4)]
    if min(sides) < min(height, width) * 0.06:
        return False, {"reason": "candidate has an implausibly short side"}
    estimated_width = (sides[0] + sides[2]) / 2
    estimated_height = (sides[1] + sides[3]) / 2
    aspect_ratio = max(estimated_width, estimated_height) / max(min(estimated_width, estimated_height), 1)
    if aspect_ratio > 6.0:
        return False, {"reason": "candidate is implausibly thin", "aspect_ratio": round(aspect_ratio, 3)}
    return True, {
        "area_ratio": round(area_ratio, 4),
        "aspect_ratio": round(aspect_ratio, 3),
    }


def _edge_support(points: np.ndarray, edges: np.ndarray) -> float:
    line_mask = np.zeros_like(edges)
    cv2.polylines(line_mask, [points.astype(np.int32)], True, 255, 5)
    supported = cv2.countNonZero(cv2.bitwise_and(edges, line_mask))
    total = max(cv2.countNonZero(line_mask), 1)
    # Exact overlap is intentionally not expected; amplify a modest match.
    return min(1.0, supported / total * 3.0)


def _candidate_score(points: np.ndarray, image_shape: tuple[int, ...], edges: np.ndarray) -> tuple[float, dict[str, float]]:
    height, width = image_shape[:2]
    image_area = float(height * width)
    contour_area = abs(float(cv2.contourArea(points)))
    area_ratio = contour_area / image_area
    area_score = min(1.0, area_ratio / 0.75)
    rectangularity = _angle_score(points)
    centroid = points.reshape(4, 2).mean(axis=0)
    distance = np.linalg.norm((centroid - np.array([width / 2, height / 2])) / np.array([width, height]))
    center_score = max(0.0, 1.0 - float(distance) * 2.0)
    edge_score = _edge_support(points.reshape(4, 2), edges)
    ordered = order_points(points)
    sides = [float(np.linalg.norm(ordered[(index + 1) % 4] - ordered[index])) for index in range(4)]
    estimated_width = (sides[0] + sides[2]) / 2
    estimated_height = (sides[1] + sides[3]) / 2
    aspect_ratio = max(estimated_width, estimated_height) / max(min(estimated_width, estimated_height), 1)
    aspect_score = max(0.0, 1.0 - max(0.0, aspect_ratio - 1.8) / 3.5)
    border_margin = min(height, width) * 0.012
    border_corners = sum(
        1
        for x, y in ordered
        if x <= border_margin or x >= width - 1 - border_margin or y <= border_margin or y >= height - 1 - border_margin
    )
    score = (
        0.42 * area_score
        + 0.23 * rectangularity
        + 0.08 * center_score
        + 0.17 * edge_score
        + 0.10 * aspect_score
        - 0.06 * border_corners
    )
    return float(np.clip(score, 0, 1)), {
        "area_ratio": round(area_ratio, 4),
        "rectangularity": round(rectangularity, 4),
        "center": round(center_score, 4),
        "edge_support": round(edge_score, 4),
        "aspect_ratio": round(aspect_ratio, 4),
        "aspect_score": round(aspect_score, 4),
        "border_corners": float(border_corners),
    }


def _preprocessing_variants(image: np.ndarray) -> list[tuple[str, np.ndarray]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    variants: list[tuple[str, np.ndarray]] = []
    for name, lower, upper in (("canny_balanced", 55, 165), ("canny_sensitive", 30, 105)):
        edges = cv2.Canny(blur, lower, upper)
        variants.append((name, cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)))
    otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    otsu_edges = cv2.Canny(otsu, 35, 120)
    variants.append(("otsu", cv2.morphologyEx(otsu_edges, cv2.MORPH_CLOSE, kernel, iterations=2)))
    return variants


def _find_contour_candidates(
    variants: list[tuple[str, np.ndarray]],
    image_shape: tuple[int, ...],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[int, ...]] = set()
    min_area = image_shape[0] * image_shape[1] * 0.15
    for variant_name, edge_map in variants:
        contours, _ = cv2.findContours(edge_map, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:20]:
            hull = cv2.convexHull(contour)
            if cv2.contourArea(hull) < min_area:
                continue
            perimeter = cv2.arcLength(hull, True)
            for epsilon in (0.015, 0.02, 0.03, 0.04):
                approximation = cv2.approxPolyDP(hull, epsilon * perimeter, True)
                if len(approximation) != 4:
                    continue
                ordered = order_points(approximation.reshape(4, 2))
                valid, _ = validate_quadrilateral(ordered, image_shape)
                if not valid:
                    continue
                signature = tuple(np.round(ordered.flatten() / 10).astype(int))
                if signature in seen:
                    continue
                seen.add(signature)
                score, components = _candidate_score(ordered, image_shape, edge_map)
                candidates.append(
                    {
                        "points": ordered,
                        "score": score,
                        "variant": variant_name,
                        "epsilon": epsilon,
                        "components": components,
                    }
                )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def _orientation_distance(first: float, second: float) -> float:
    difference = abs(first - second) % np.pi
    return min(difference, np.pi - difference)


def _line_intersection(first: np.ndarray, second: np.ndarray) -> np.ndarray | None:
    p, p2 = first[:2], first[2:]
    q, q2 = second[:2], second[2:]
    r, s = p2 - p, q2 - q
    denominator = float(r[0] * s[1] - r[1] * s[0])
    if abs(denominator) < 1e-5:
        return None
    q_minus_p = q - p
    t = float((q_minus_p[0] * s[1] - q_minus_p[1] * s[0]) / denominator)
    return (p + t * r).astype(np.float32)


def _outer_boundary_lines(
    lines: list[dict[str, Any]],
    dominant_angle: float,
) -> tuple[np.ndarray, np.ndarray] | None:
    if len(lines) < 2:
        return None
    normal = np.array([-np.sin(dominant_angle), np.cos(dominant_angle)], dtype=np.float32)
    ranked = sorted(lines, key=lambda item: float(np.dot(item["midpoint"], normal)))
    # Only compare a few truly outer lines. A broad quartile can let long text
    # baselines beat a shorter, broken page border.
    outer_count = max(1, min(3, len(ranked) // 4))
    low = max(ranked[:outer_count], key=lambda item: item["length"])
    high = max(ranked[-outer_count:], key=lambda item: item["length"])
    if float(np.dot(high["midpoint"] - low["midpoint"], normal)) < 0.18 * min(lines[0]["image_shape"][:2]):
        return None
    return low["line"], high["line"]


def _find_hough_candidate(
    edges: np.ndarray,
    image_shape: tuple[int, ...],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    height, width = image_shape[:2]
    minimum_dimension = min(height, width)
    detected = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=max(45, int(minimum_dimension * 0.07)),
        minLineLength=max(40, int(minimum_dimension * 0.22)),
        maxLineGap=max(18, int(minimum_dimension * 0.055)),
    )
    if detected is None:
        return None, {"line_count": 0, "reason": "no long Hough lines"}

    lines: list[dict[str, Any]] = []
    for raw in detected[:, 0, :]:
        line = raw.astype(np.float32)
        delta = line[2:] - line[:2]
        length = float(np.linalg.norm(delta))
        if length < minimum_dimension * 0.22:
            continue
        angle = float(np.arctan2(delta[1], delta[0]) % np.pi)
        lines.append(
            {
                "line": line,
                "length": length,
                "angle": angle,
                "midpoint": (line[:2] + line[2:]) / 2,
                "image_shape": image_shape,
            }
        )
    if len(lines) < 4:
        return None, {"line_count": len(lines), "reason": "fewer than four long Hough lines"}

    bin_count = 18
    weights = np.zeros(bin_count, dtype=np.float32)
    for line in lines:
        bin_index = min(bin_count - 1, int(line["angle"] / np.pi * bin_count))
        weights[bin_index] += line["length"]
    primary_bin = int(np.argmax(weights))
    primary_angle = (primary_bin + 0.5) * np.pi / bin_count
    eligible = [
        index
        for index in range(bin_count)
        if np.deg2rad(55) <= _orientation_distance(primary_angle, (index + 0.5) * np.pi / bin_count) <= np.deg2rad(90)
    ]
    if not eligible:
        return None, {"line_count": len(lines), "reason": "no perpendicular orientation group"}
    secondary_bin = max(eligible, key=lambda index: float(weights[index]))
    if weights[secondary_bin] <= 0:
        return None, {"line_count": len(lines), "reason": "second orientation group is empty"}
    secondary_angle = (secondary_bin + 0.5) * np.pi / bin_count
    tolerance = np.deg2rad(18)
    first_group = [line for line in lines if _orientation_distance(line["angle"], primary_angle) <= tolerance]
    second_group = [line for line in lines if _orientation_distance(line["angle"], secondary_angle) <= tolerance]
    first_bounds = _outer_boundary_lines(first_group, primary_angle)
    second_bounds = _outer_boundary_lines(second_group, secondary_angle)
    debug = {
        "line_count": len(lines),
        "orientation_degrees": [round(float(np.rad2deg(primary_angle)), 1), round(float(np.rad2deg(secondary_angle)), 1)],
        "orientation_group_sizes": [len(first_group), len(second_group)],
    }
    if first_bounds is None or second_bounds is None:
        debug["reason"] = "could not select separated outer lines"
        return None, debug

    intersections = [
        _line_intersection(first_bounds[0], second_bounds[0]),
        _line_intersection(first_bounds[1], second_bounds[0]),
        _line_intersection(first_bounds[1], second_bounds[1]),
        _line_intersection(first_bounds[0], second_bounds[1]),
    ]
    if any(point is None for point in intersections):
        debug["reason"] = "outer lines did not produce four intersections"
        return None, debug
    points = order_points(np.asarray(intersections, dtype=np.float32))
    valid, validation = validate_quadrilateral(points, image_shape)
    if not valid:
        debug.update({"reason": validation.get("reason", "invalid Hough quadrilateral")})
        return None, debug
    score, components = _candidate_score(points, image_shape, edges)
    candidate = {
        "points": points,
        "score": float(np.clip(score * 0.94, 0, 1)),
        "components": components,
    }
    return candidate, debug


def _find_min_area_rect_candidate(
    edges: np.ndarray,
    image_shape: tuple[int, ...],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    connected = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    connected = cv2.dilate(connected, kernel, iterations=1)
    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    debug: dict[str, Any] = {"region_count": len(contours)}
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
        if cv2.contourArea(cv2.convexHull(contour)) < image_shape[0] * image_shape[1] * 0.12:
            continue
        points = order_points(cv2.boxPoints(cv2.minAreaRect(contour)))
        valid, validation = validate_quadrilateral(points, image_shape, min_area_ratio=0.12)
        if not valid:
            continue
        score, components = _candidate_score(points, image_shape, edges)
        # This fallback does not recover perspective, so it always needs review.
        confidence = min(0.49, score * 0.68)
        return {"points": points, "score": confidence, "components": components}, debug
    debug["reason"] = "no plausible foreground region for minAreaRect"
    return None, debug


def detect_document_corners(image: np.ndarray, detection_long_edge: int = 1400) -> DetectionResult:
    height, width = image.shape[:2]
    longest = max(height, width)
    scale = min(1.0, detection_long_edge / longest)
    resized = (
        cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
        if scale < 1
        else image.copy()
    )
    variants = _preprocessing_variants(resized)
    combined_edges = np.zeros(resized.shape[:2], dtype=np.uint8)
    for _, edge_map in variants:
        combined_edges = cv2.bitwise_or(combined_edges, edge_map)
    contour_candidates = _find_contour_candidates(variants, resized.shape)
    debug: dict[str, Any] = {
        "original_dimensions": {"width": width, "height": height},
        "processed_dimensions": {"width": resized.shape[1], "height": resized.shape[0]},
        "scale": round(scale, 6),
        "candidate_count": len(contour_candidates),
        "contour_candidate_count": len(contour_candidates),
        "hough_fallback_ran": False,
        "min_area_rect_fallback_ran": False,
    }
    selected: dict[str, Any] | None = contour_candidates[0] if contour_candidates else None
    selected_method = "contour" if selected is not None else "none"

    if selected is None or selected["score"] < settings.scan_confidence_threshold:
        debug["hough_fallback_ran"] = True
        hough_candidate, hough_debug = _find_hough_candidate(combined_edges, resized.shape)
        debug["hough"] = hough_debug
        if hough_candidate is not None and hough_candidate["score"] >= 0.52:
            selected = hough_candidate
            selected_method = "hough"
        else:
            debug["min_area_rect_fallback_ran"] = True
            min_rect_candidate, min_rect_debug = _find_min_area_rect_candidate(combined_edges, resized.shape)
            debug["min_area_rect"] = min_rect_debug
            if min_rect_candidate is not None:
                selected = min_rect_candidate
                selected_method = "min_area_rect"
            elif selected is None and hough_candidate is not None:
                selected = hough_candidate
                selected_method = "hough"

    if selected is None:
        debug.update(
            {
                "detection_method": "none",
                "selected_method": "none",
                "selected_confidence": 0.0,
                "reason": "all corner detectors failed",
            }
        )
        return DetectionResult(corners=None, confidence=0.0, method="none", debug_info=debug)

    original_points = order_points(selected["points"] / scale)
    debug.update({
        "detection_method": selected_method,
        "selected_method": selected_method,
        "selected_confidence": round(selected["score"], 4),
        "selected_pass": selected.get("variant"),
        "selected_epsilon": selected.get("epsilon"),
        "selected_corners": np.round(original_points, 1).tolist(),
        "score_components": selected["components"],
        "top_candidates": [
            {
                "pass": candidate["variant"],
                "epsilon": candidate["epsilon"],
                "score": round(candidate["score"], 4),
                "points": np.round(candidate["points"] / scale, 1).tolist(),
            }
            for candidate in contour_candidates[:5]
        ],
    })
    return DetectionResult(
        corners=original_points,
        confidence=round(selected["score"], 4),
        method=selected_method,
        debug_info=debug,
    )


def perspective_transform(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
    top_left, top_right, bottom_right, bottom_left = order_points(corners)
    width = max(np.linalg.norm(bottom_right - bottom_left), np.linalg.norm(top_right - top_left))
    height = max(np.linalg.norm(top_right - bottom_right), np.linalg.norm(top_left - bottom_left))
    target_width, target_height = max(1, round(width)), max(1, round(height))
    destination = np.array(
        [[0, 0], [target_width - 1, 0], [target_width - 1, target_height - 1], [0, target_height - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(order_points(corners), destination)
    return cv2.warpPerspective(image, matrix, (target_width, target_height))


def enhance_color_scan(image: np.ndarray) -> np.ndarray:
    """Create a natural-looking color scan while preserving annotations."""
    denoised = cv2.fastNlMeansDenoisingColored(
        image,
        None,
        h=settings.scan_denoise_strength,
        hColor=settings.scan_denoise_strength,
        templateWindowSize=7,
        searchWindowSize=21,
    )
    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    lightness, channel_a, channel_b = cv2.split(lab)

    background = cv2.GaussianBlur(lightness, (0, 0), sigmaX=settings.scan_background_sigma)
    normalized = cv2.divide(lightness, np.maximum(background, 1), scale=255)
    tile_size = max(1, settings.scan_clahe_tile_size)
    enhanced_lightness = cv2.createCLAHE(
        clipLimit=settings.scan_clahe_clip_limit,
        tileGridSize=(tile_size, tile_size),
    ).apply(normalized)

    result_lab = cv2.merge((enhanced_lightness, channel_a, channel_b))
    result = cv2.cvtColor(result_lab, cv2.COLOR_LAB2BGR)
    blurred = cv2.GaussianBlur(result, (0, 0), sigmaX=1.0)
    amount = max(0.0, settings.scan_sharpen_amount)
    return cv2.addWeighted(result, 1.0 + amount, blurred, -amount, 0)


def make_bw_scan(image: np.ndarray) -> np.ndarray:
    """Create a clean monochrome derivative for printing and OCR testing."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(
        gray,
        None,
        h=5,
        templateWindowSize=7,
        searchWindowSize=21,
    )
    background = cv2.GaussianBlur(gray, (0, 0), sigmaX=settings.scan_background_sigma)
    normalized = cv2.divide(gray, np.maximum(background, 1), scale=255)
    block_size = max(3, settings.scan_bw_block_size)
    if block_size % 2 == 0:
        block_size += 1
    return cv2.adaptiveThreshold(
        normalized,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        settings.scan_bw_c,
    )


def _post_process_scan(corrected: np.ndarray, detection: DetectionResult) -> ScanResult:
    processing_debug: dict[str, Any] = {
        "denoise_strength": settings.scan_denoise_strength,
        "background_sigma": settings.scan_background_sigma,
        "clahe_clip_limit": settings.scan_clahe_clip_limit,
        "sharpen_amount": settings.scan_sharpen_amount,
    }

    try:
        color = enhance_color_scan(corrected)
        processing_debug["color_enhancement"] = "complete"
    except Exception as exc:
        # Enhancement must never discard an otherwise usable perspective warp.
        color = corrected.copy()
        processing_debug["color_enhancement"] = "fallback_to_warp"
        processing_debug["color_enhancement_error"] = f"{type(exc).__name__}: {exc}"

    try:
        black_and_white = make_bw_scan(corrected)
        processing_debug["black_and_white"] = "complete"
    except Exception as exc:
        # A grayscale derivative remains useful if thresholding ever fails.
        black_and_white = cv2.cvtColor(corrected, cv2.COLOR_BGR2GRAY)
        processing_debug["black_and_white"] = "fallback_to_grayscale"
        processing_debug["black_and_white_error"] = f"{type(exc).__name__}: {exc}"

    detection.debug_info["post_processing"] = processing_debug
    return ScanResult(color=color, black_and_white=black_and_white, detection=detection)


def scan_document(image: np.ndarray) -> ScanResult:
    detection = detect_document_corners(image)
    corrected = perspective_transform(image, detection.corners) if detection.corners is not None else image.copy()
    return _post_process_scan(corrected, detection)


def scan_document_with_corners(image: np.ndarray, corners: np.ndarray) -> ScanResult:
    """Create an authoritative scan from four user-confirmed source-image points."""
    valid, validation = validate_quadrilateral(corners, image.shape, min_area_ratio=0.01)
    if not valid:
        raise ValueError(str(validation.get("reason", "The selected corners are invalid.")))
    ordered = order_points(corners)
    corrected = perspective_transform(image, ordered)
    detection = DetectionResult(
        corners=ordered,
        confidence=1.0,
        method="manual",
        debug_info={
            "detection_method": "manual",
            "selected_method": "manual",
            "selected_confidence": 1.0,
            "selected_corners": np.round(ordered, 1).tolist(),
            "validation": validation,
        },
    )
    return _post_process_scan(corrected, detection)


def corners_to_json(corners: np.ndarray | None) -> dict[str, list[float]] | None:
    if corners is None:
        return None
    ordered = order_points(corners)
    labels = ("top_left", "top_right", "bottom_right", "bottom_left")
    return {label: [round(float(x), 2), round(float(y), 2)] for label, (x, y) in zip(labels, ordered)}
