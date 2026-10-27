"""Apply layout exclusions after cropping, retaining original click geometry."""
import numpy as np


def apply_exclusions(template, rectangles, name):
    if not rectangles:
        return template.copy()
    height, width = template.shape[:2]
    mask = np.full((height, width), 255, dtype=np.uint8)
    for x, y, w, h in rectangles:
        if min(x, y) < 0 or min(w, h) <= 0 or x+w > width or y+h > height:
            raise ValueError(f'Invalid marker exclusion: {name}')
        mask[y:y+h, x:x+w] = 0
    if not np.any(mask):
        raise ValueError(f'Empty marker mask: {name}')
    return np.dstack((template[:, :, :3], mask))


def color_error(sample, template):
    delta = np.abs(sample.astype(np.float32) - template[:, :, :3]).mean(axis=2)
    if template.shape[2] == 4:
        delta = delta[template[:, :, 3] > 0]
    return float(delta.mean() / 255)


def matches_fixed_mask(sample, template, threshold, max_error):
    """Compare a known, single-position panel without a large FFT search."""
    keep = template[:, :, 3] > 0
    actual = sample[keep].astype(np.float32)
    reference = template[:, :, :3][keep].astype(np.float32)
    difference = actual - reference
    error = float(np.abs(difference).mean() / 255)
    color = 1 - float(np.sqrt(np.square(difference).mean()) / 255)
    if error > max_error or color < threshold:
        return False
    actual -= actual.mean(axis=0)
    reference -= reference.mean(axis=0)
    denominator = float(np.sqrt(np.square(actual).sum() * np.square(reference).sum()))
    if denominator <= 0:
        return False
    shape = float((actual * reference).sum()) / denominator
    return shape >= threshold
