import cairo
from dataclasses import dataclass

@dataclass
class Rect:
    x: int
    y: int
    width: int
    height: int

_scratch: cairo.ImageSurface | None = None


def _scratch_surface(width: int, height: int) -> cairo.ImageSurface:
    global _scratch
    if (
        _scratch is None
        or _scratch.get_width() != width
        or _scratch.get_height() != height
    ):
        _scratch = cairo.ImageSurface(cairo.Format.A8, width, height)
    return _scratch


def release_scratch_surface():
    """Drop the shared trace buffer. Only useful when shutting down."""
    global _scratch
    _scratch = None


def trace_widget_regions(widget, accuracy=2, alpha_threshold=20, erode=4):
    alloc = widget.get_allocation()
    w, h = alloc.width, alloc.height
    if w <= 0 or h <= 0:
        return []

    surface = _scratch_surface(w, h)
    cr = cairo.Context(surface)
    cr.set_operator(cairo.OPERATOR_CLEAR)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    widget.draw(cr)
    surface.flush()

    data   = surface.get_data()
    stride = surface.get_stride()

    raw = []
    for y in range(0, h, accuracy):
        step_h = min(accuracy, h - y)
        x = 0
        while x < w:
            if data[y * stride + x] > alpha_threshold:
                start_x = x
                while x < w and data[y * stride + x] > alpha_threshold:
                    x += 1
                raw.append(Rect(start_x, y, x - start_x, step_h))
            else:
                x += 1

    active: dict[tuple, Rect] = {}
    merged: list[Rect] = []
    for rect in raw:
        key = (rect.x, rect.width)
        if key in active:
            m = active[key]
            if m.y + m.height == rect.y:
                m.height += rect.height
                continue
            else:
                merged.append(active.pop(key))
        active[key] = Rect(rect.x, rect.y, rect.width, rect.height)

    merged.extend(active.values())
    if erode <= 0:
        return merged

    if not merged:
        return merged

    min_y = min(r.y for r in merged)
    max_y = max(r.y + r.height for r in merged)

    result = []
    for r in merged:
        new_x = r.x + erode
        new_w = r.width - (erode * 2)
        
        base_y = max(r.y, min_y + erode)
        
        new_y = base_y - 2 
        
        base_bottom = min(r.y + r.height, max_y - erode)
        new_h = base_bottom - base_y
        
        if new_w > 0 and new_h > 0:
            result.append(Rect(new_x, new_y, new_w, new_h))
    return result
def trace_widget_regions_as_dicts(widget, accuracy=10, alpha_threshold=10, erode=0):
    return [
        {"x": r.x, "y": r.y, "width": r.width, "height": r.height}
        for r in trace_widget_regions(widget, accuracy, alpha_threshold, erode)
    ]

_THRESHOLD_TABLES: dict[int, bytes] = {}

_EXACT_PEAK_LIMIT = 1 << 16
_PEAK_STRIDE = 31


def _peak_alpha(alpha: bytes) -> int:
    if len(alpha) <= _EXACT_PEAK_LIMIT:
        return max(alpha)
    return max(alpha[::_PEAK_STRIDE])


def _threshold_table(threshold: int) -> bytes:
    table = _THRESHOLD_TABLES.get(threshold)
    if table is None:
        table = bytes(1 if value > threshold else 0 for value in range(256))
        _THRESHOLD_TABLES[threshold] = table
    return table


def regions_from_alpha(
    alpha: bytes,
    width: int,
    height: int,
    min_alpha: int = 8,
    relative_alpha: float = 0.0,
    flip_y: bool = False,
    out_width: int | None = None,
    out_height: int | None = None,
    inset: int = 0,
) -> list[Rect]:
    if width <= 0 or height <= 0 or not alpha:
        return []

    peak = _peak_alpha(alpha)
    if peak == 0:
        return []

    threshold = max(min_alpha, int(peak * relative_alpha))
    mask = alpha.translate(_threshold_table(threshold))

    find = mask.find
    view = memoryview(mask)
    open_runs: dict[tuple[int, int], int] = {}
    grid: list[tuple[int, int, int, int]] = []
    runs: list[tuple[int, int]] = []
    previous = -1

    scan = range(height - 1, -1, -1) if flip_y else range(height)
    for out_y, y in enumerate(scan):
        base    = y * width
        row_end = base + width

        if previous >= 0 and view[base:row_end] == view[previous:previous + width]:
            previous = base
            continue
        previous = base

        runs = []
        start = find(1, base, row_end)
        while start != -1:
            stop = find(0, start, row_end)
            if stop == -1:
                stop = row_end
            runs.append((start - base, stop - base))
            start = find(1, stop, row_end)

        current = set(runs)
        for run in [r for r in open_runs if r not in current]:
            grid.append((run[0], open_runs.pop(run), run[1], out_y))
        for run in runs:
            open_runs.setdefault(run, out_y)

    for run, top in open_runs.items():
        grid.append((run[0], top, run[1], height))

    scale_x = (out_width / width) if out_width else 1.0
    scale_y = (out_height / height) if out_height else 1.0

    top_limit = bottom_limit = 0
    if inset and grid:
        top_limit    = round(min(g[1] for g in grid) * scale_y) + inset
        bottom_limit = round(max(g[3] for g in grid) * scale_y) - inset

    rects: list[Rect] = []
    for x0, y0, x1, y1 in grid:
        left   = round(x0 * scale_x) + inset
        right  = round(x1 * scale_x) - inset
        top    = round(y0 * scale_y)
        bottom = round(y1 * scale_y)
        if inset:
            top    = max(top, top_limit)
            bottom = min(bottom, bottom_limit)
        if right > left and bottom > top:
            rects.append(Rect(left, top, right - left, bottom - top))
    return rects


def widget_alpha(widget, step: int = 1) -> tuple[bytes, int, int]:
    step = max(1, step)
    alloc = widget.get_allocation()
    w, h = alloc.width, alloc.height
    if w <= 0 or h <= 0:
        return b"", 0, 0

    surface = _scratch_surface(w, h)
    cr = cairo.Context(surface)
    cr.set_operator(cairo.OPERATOR_CLEAR)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    widget.draw(cr)
    surface.flush()

    stride = surface.get_stride()
    raw = bytes(surface.get_data())

    if step == 1:
        if stride == w:
            return raw, w, h
        return (
            b"".join(raw[y * stride : y * stride + w] for y in range(h)),
            w, h,
        )

    sw = -(-w // step)
    sh = -(-h // step)
    row = step * stride
    plane = b"".join(
        raw[y * row : y * row + w : step] for y in range(sh)
    )
    return plane, sw, sh


def trace_widget(
    widget,
    min_alpha: int = 8,
    relative_alpha: float = 0.5,
    inset: int = 0,
    step: int = 1,
) -> list[Rect]:
    """Regions covered by ``widget`` as GTK currently draws it."""
    alloc = widget.get_allocation()
    alpha, w, h = widget_alpha(widget, step=step)
    return regions_from_alpha(
        alpha, w, h,
        min_alpha=min_alpha,
        relative_alpha=relative_alpha,
        out_width=alloc.width,
        out_height=alloc.height,
        inset=inset,
    )
