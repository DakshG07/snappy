import cv2
import numpy as np
import pytest

from app.services import scanner
from app.services.scanner import (
    detect_document_corners,
    enhance_color_scan,
    make_bw_scan,
    order_points,
    perspective_transform,
    scan_document,
    scan_document_with_corners,
    validate_quadrilateral,
)


def synthetic_document() -> np.ndarray:
    image = np.full((900, 1200, 3), (55, 64, 72), dtype=np.uint8)
    page = np.array([[205, 120], [1020, 185], [945, 785], [145, 720]], dtype=np.int32)
    cv2.fillConvexPoly(image, page, (242, 245, 244))
    for y in range(260, 650, 55):
        cv2.line(image, (265, y), (850, y + 45), (85, 85, 85), 8)
    return image


def test_order_points_returns_expected_order() -> None:
    points = np.array([[90, 80], [10, 10], [15, 90], [100, 20]], dtype=np.float32)
    ordered = order_points(points)
    assert np.allclose(ordered[0], [10, 10])
    assert np.allclose(ordered[1], [100, 20])
    assert np.allclose(ordered[2], [90, 80])
    assert np.allclose(ordered[3], [15, 90])


def test_detects_and_transforms_a_page() -> None:
    image = synthetic_document()
    result = detect_document_corners(image)
    assert result.corners is not None
    assert result.confidence >= 0.6
    assert result.method == "contour"
    transformed = perspective_transform(image, result.corners)
    assert transformed.shape[0] > 500
    assert transformed.shape[1] > 700


def test_blank_image_degrades_to_fallback_scan() -> None:
    image = np.full((500, 700, 3), 128, dtype=np.uint8)
    result = scan_document(image)
    assert result.detection.corners is None
    assert result.detection.confidence == 0
    assert result.detection.method == "none"
    assert result.color.shape == image.shape


def test_manual_corners_create_authoritative_scan() -> None:
    image = synthetic_document()
    corners = np.array([[205, 120], [1020, 185], [945, 785], [145, 720]], dtype=np.float32)

    result = scan_document_with_corners(image, corners)

    assert result.detection.method == "manual"
    assert result.detection.confidence == 1.0
    assert result.detection.debug_info["selected_method"] == "manual"
    assert result.color.shape[0] > 500
    assert result.color.shape[1] > 700
    assert result.black_and_white.shape == result.color.shape[:2]


def test_shared_validation_rejects_degenerate_points() -> None:
    duplicate = np.array([[20, 20], [20, 20], [480, 330], [20, 330]], dtype=np.float32)
    valid, debug = validate_quadrilateral(duplicate, (400, 600, 3))
    assert not valid
    assert "identical" in str(debug["reason"])


def test_hough_fallback_recovers_broken_page_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    image = np.full((800, 1000, 3), 45, dtype=np.uint8)
    segments = [
        ((170, 140), (480, 165)), ((535, 170), (850, 195)),
        ((850, 195), (820, 455)), ((815, 515), (790, 690)),
        ((790, 690), (500, 665)), ((445, 660), (130, 635)),
        ((130, 635), (145, 410)), ((150, 350), (170, 140)),
    ]
    for start, end in segments:
        cv2.line(image, start, end, (245, 245, 245), 7)
    for y in range(270, 570, 55):
        cv2.line(image, (250, y), (700, y + 18), (150, 150, 150), 3)
    monkeypatch.setattr(scanner, "_find_contour_candidates", lambda variants, shape: [])

    result = detect_document_corners(image)

    assert result.method == "hough"
    assert result.corners is not None
    assert result.confidence >= 0.6
    assert result.debug_info["hough_fallback_ran"] is True
    assert result.debug_info["hough"]["line_count"] >= 4


def test_min_area_rect_fallback_returns_reviewable_corners(monkeypatch: pytest.MonkeyPatch) -> None:
    image = np.full((700, 900, 3), 35, dtype=np.uint8)
    page = cv2.boxPoints(((450, 350), (590, 410), -13)).astype(np.int32)
    cv2.fillConvexPoly(image, page, (225, 225, 225))
    monkeypatch.setattr(scanner, "_find_contour_candidates", lambda variants, shape: [])
    monkeypatch.setattr(scanner, "_find_hough_candidate", lambda edges, shape: (None, {"reason": "forced"}))

    result = detect_document_corners(image)

    assert result.method == "min_area_rect"
    assert result.corners is not None
    assert 0 < result.confidence < 0.6
    assert result.debug_info["hough_fallback_ran"] is True
    assert result.debug_info["min_area_rect_fallback_ran"] is True


def unevenly_lit_page() -> np.ndarray:
    height, width = 360, 560
    illumination = np.linspace(155, 238, width, dtype=np.uint8)
    page = np.repeat(illumination[np.newaxis, :], height, axis=0)
    image = cv2.merge((page, page, page))
    cv2.putText(image, "Momentum and Impulse", (45, 105), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (35, 35, 35), 2)
    cv2.putText(image, "F = change in momentum / time", (45, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (45, 45, 45), 1)
    cv2.rectangle(image, (75, 220), (330, 255), (20, 215, 245), -1)
    cv2.putText(image, "highlighted note", (88, 246), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (30, 30, 30), 1)
    noise = np.random.default_rng(7).normal(0, 4, image.shape).astype(np.int16)
    return np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def test_color_enhancement_normalizes_lighting_and_preserves_color() -> None:
    image = unevenly_lit_page()
    enhanced = enhance_color_scan(image)
    before_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    after_gray = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)

    before_delta = abs(float(before_gray[280:330, 20:120].mean()) - float(before_gray[280:330, 440:540].mean()))
    after_delta = abs(float(after_gray[280:330, 20:120].mean()) - float(after_gray[280:330, 440:540].mean()))
    assert enhanced.shape == image.shape
    assert enhanced.dtype == np.uint8
    assert after_delta < before_delta * 0.4

    highlighted = cv2.cvtColor(enhanced[225:250, 100:300], cv2.COLOR_BGR2HSV)
    assert float(highlighted[:, :, 1].mean()) > 65


def test_bw_scan_is_binary() -> None:
    bw = make_bw_scan(unevenly_lit_page())
    assert bw.ndim == 2
    assert set(np.unique(bw)).issubset({0, 255})


def test_enhancement_failure_falls_back_to_perspective_warp(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_enhancement(_: np.ndarray) -> np.ndarray:
        raise RuntimeError("simulated enhancement failure")

    image = synthetic_document()
    detection = detect_document_corners(image)
    assert detection.corners is not None
    expected = perspective_transform(image, detection.corners)
    monkeypatch.setattr(scanner, "enhance_color_scan", fail_enhancement)

    result = scan_document(image)

    assert np.array_equal(result.color, expected)
    post_processing = result.detection.debug_info["post_processing"]
    assert post_processing["color_enhancement"] == "fallback_to_warp"
    assert "simulated enhancement failure" in post_processing["color_enhancement_error"]
