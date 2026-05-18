"""Tests for pure-Python crop / paste helpers used by Florence2 Hi-Res Fix."""
import pytest
import torch

from florence2_hires import _crop_image_by_mask


def _make_image(w, h):
    """Make a deterministic (1, H, W, 3) image where pixel value encodes its (x, y)."""
    img = torch.zeros((1, h, w, 3), dtype=torch.float32)
    for y in range(h):
        for x in range(w):
            img[0, y, x, 0] = x / max(w - 1, 1)
            img[0, y, x, 1] = y / max(h - 1, 1)
            img[0, y, x, 2] = 0.5
    return img


def _make_centered_mask(w, h, box_w, box_h):
    """Make a (1, H, W) mask with a centered rectangle of 1.0s."""
    mask = torch.zeros((1, h, w), dtype=torch.float32)
    cx, cy = w // 2, h // 2
    x0 = cx - box_w // 2
    y0 = cy - box_h // 2
    mask[0, y0:y0 + box_h, x0:x0 + box_w] = 1.0
    return mask


def test_crop_centered_box_no_padding():
    img = _make_image(512, 512)
    mask = _make_centered_mask(512, 512, 100, 100)
    cropped_img, cropped_mask, bbox = _crop_image_by_mask(
        img, mask, padding=0, min_crop_resolution=0, max_crop_resolution=99999
    )
    x0, y0, bw, bh = bbox
    # Box is 100x100 centered -> x0=206, y0=206, w=100, h=100
    assert bw == 100 and bh == 100
    assert x0 == 206 and y0 == 206
    assert cropped_img.shape == (1, 100, 100, 3)
    assert cropped_mask.shape == (1, 100, 100)


def test_crop_with_padding_expands_bbox():
    img = _make_image(512, 512)
    mask = _make_centered_mask(512, 512, 100, 100)
    cropped_img, cropped_mask, bbox = _crop_image_by_mask(
        img, mask, padding=32, min_crop_resolution=0, max_crop_resolution=99999
    )
    x0, y0, bw, bh = bbox
    assert bw == 164 and bh == 164  # 100 + 2*32
    assert x0 == 174 and y0 == 174


def test_crop_padding_clamped_at_image_edge():
    """Mask at top-left corner with huge padding -> bbox starts at (0, 0)."""
    img = _make_image(512, 512)
    mask = torch.zeros((1, 512, 512), dtype=torch.float32)
    mask[0, 0:50, 0:50] = 1.0
    cropped_img, cropped_mask, bbox = _crop_image_by_mask(
        img, mask, padding=200, min_crop_resolution=0, max_crop_resolution=99999
    )
    x0, y0, bw, bh = bbox
    assert x0 == 0 and y0 == 0
    assert bw == 250 and bh == 250  # 50 + 200 (clamped on top-left side)


def test_min_crop_resolution_expands_tiny_bbox():
    """20px mask + min_crop_resolution=200 -> bbox grows to >=200."""
    img = _make_image(512, 512)
    mask = _make_centered_mask(512, 512, 20, 20)
    cropped_img, cropped_mask, bbox = _crop_image_by_mask(
        img, mask, padding=0, min_crop_resolution=200, max_crop_resolution=99999
    )
    _, _, bw, bh = bbox
    assert bw >= 200 and bh >= 200


def test_max_crop_resolution_caps_huge_bbox():
    """400px mask + max_crop_resolution=200 -> bbox capped at 200."""
    img = _make_image(512, 512)
    mask = _make_centered_mask(512, 512, 400, 400)
    cropped_img, cropped_mask, bbox = _crop_image_by_mask(
        img, mask, padding=0, min_crop_resolution=0, max_crop_resolution=200
    )
    _, _, bw, bh = bbox
    assert bw <= 200 and bh <= 200


def test_empty_mask_raises():
    """Empty mask should raise — caller is responsible for no-detection check."""
    img = _make_image(512, 512)
    mask = torch.zeros((1, 512, 512), dtype=torch.float32)
    with pytest.raises(ValueError):
        _crop_image_by_mask(img, mask, padding=0, min_crop_resolution=0, max_crop_resolution=99999)
