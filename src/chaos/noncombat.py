"""Locate menu outlines after the caller has verified a node's scene symbols."""
import cv2
import numpy as np


def _outline(width, height):
    radius = 16
    model = np.zeros((height, width), np.float32)
    cv2.line(model, (radius, 2), (width-radius-1, 2), 1)
    cv2.line(model, (radius, height-3), (width-radius-1, height-3), 1)
    cv2.line(model, (2, radius), (2, height-radius-1), 1)
    cv2.line(model, (width-3, radius), (width-3, height-radius-1), 1)
    for center, start, end in (((radius, radius), 180, 270),
                               ((width-radius-1, radius), 270, 360),
                               ((radius, height-radius-1), 90, 180),
                               ((width-radius-1, height-radius-1), 0, 90)):
        cv2.ellipse(model, center, (radius-2, radius-2), 0, start, end, 1, 1)
    model[30:66, width-20:width] = 0  # animated sparkle on the right edge
    return model


MENU_OUTLINE = _outline(330, 94)


def menu_bounds(screen, expected):
    """Search around the expected layout; never return unchecked fixed coordinates.

    Only the perimeter contributes. Text, translucency, and the central sparkle
    have no weight. Require every corner as well as the overall outline.
    """
    x, y, width, height = expected
    if (width, height) != (330, 94):
        return None
    pad = 16
    x0, y0 = max(0, x-pad), max(0, y-pad)
    sample = screen[y0:min(screen.shape[0], y+height+pad),
                    x0:min(screen.shape[1], x+width+pad), :3]
    if sample.shape[0] < height or sample.shape[1] < width:
        return None
    gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 20, 50)
    nearby = (cv2.dilate(edges, np.ones((5, 5), np.uint8)) > 0).astype(np.float32)
    scores = cv2.matchTemplate(nearby, MENU_OUTLINE, cv2.TM_CCORR) / MENU_OUTLINE.sum()
    candidates = np.argwhere(scores >= .93)
    # Once the strict outline threshold is met, prefer the closest layout.
    # Text noise inside a neighbouring offset must not outrank the real frame.
    candidates = sorted(candidates, key=lambda p: (
                        abs(x0+int(p[1])-x)+abs(y0+int(p[0])-y),
                        -float(scores[tuple(p)])))
    corners = ((0, 0), (width-18, 0), (0, height-18), (width-18, height-18))
    for my, mx in candidates:
        area = nearby[my:my+height, mx:mx+width]
        if all(float((area[cy:cy+18, cx:cx+18] * MENU_OUTLINE[cy:cy+18, cx:cx+18]).sum())
               / float(MENU_OUTLINE[cy:cy+18, cx:cx+18].sum()) >= .8 for cx, cy in corners):
            return (x0+int(mx), y0+int(my), width, height)
    return None


def menu_stack(screen, expected_rows):
    bounds = [menu_bounds(screen, row) for row in expected_rows]
    if not all(bounds):
        return None
    if max(b[0] for b in bounds)-min(b[0] for b in bounds) > 4:
        return None
    if any(abs((b[1]-a[1])-(ey[1]-ex[1])) > 4
           for a, b, ex, ey in zip(bounds, bounds[1:], expected_rows, expected_rows[1:])):
        return None
    return bounds


def active_menu(screen, bounds, active, inactive):
    """Compare both states at the detected position; an ambiguous state is inert."""
    x, y, w, h = bounds
    # Geometry localization tolerates a couple of edge pixels. Evaluate the
    # references with the same offset so brightness comparisons stay meaningful.
    best = None
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            sample = screen[y+dy:y+dy+h, x+dx:x+dx+w, :3].astype(np.float32)
            if sample.shape[:2] != (h, w):
                continue
            errors = []
            for template in (active, inactive):
                keep = template[:, :, 3] > 0
                errors.append(float(np.abs(sample-template[:, :, :3])[keep].mean()/255))
            if best is None or errors[0] < best[0]:
                best = errors
    return bool(best and best[0] <= .08 and best[1]-best[0] >= .008)
