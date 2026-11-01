"""Plane geometry for the gate's position rules (H7 part outline, H8 keep-outs).

Arithmetic: IEEE 754 double in device units (0.01 mm). The head positions are
exact integers; the outline and keep-out vertices come from library mm values
times UNITS_PER_MM and may carry representation error (2.3 mm * 100 is
229.99999999999997). Every comparison against a boundary therefore allows
EPS = 1e-6 units (1e-8 mm), a million times smaller than one device unit, so a
point that lies exactly on a boundary in mm is judged as on it, and a point
one unit (0.01 mm) away is always on the correct side. Only +, -, * and / are
used (no sqrt, no libm), so the result is the same on every IEEE platform.

Semantics:
  * Polygons are closed sets: a point on the boundary is inside (closed).
  * `clearance_ok(d2, m)`: the distance (given squared) is at least m, with EPS.
  * `segment_pieces_inside` splits a segment at every boundary crossing and
    tests the midpoint of each piece, so concave outlines and holes are exact.
"""
from __future__ import annotations

from collections.abc import Sequence

FPt = tuple[float, float]
Poly = Sequence[FPt]

EPS = 1e-6   # device units


def _sub(a: FPt, b: FPt) -> FPt:
    return (a[0] - b[0], a[1] - b[1])


def _cross(a: FPt, b: FPt) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _dot(a: FPt, b: FPt) -> float:
    return a[0] * b[0] + a[1] * b[1]


def edges(poly: Poly) -> list[tuple[FPt, FPt]]:
    """The polygon's edges, closing the last vertex to the first."""
    n = len(poly)
    return [(poly[i], poly[(i + 1) % n]) for i in range(n)] if n >= 2 else []


def point_segment_dist2(p: FPt, a: FPt, b: FPt) -> float:
    """Squared distance from p to the closed segment ab."""
    ab = _sub(b, a)
    ap = _sub(p, a)
    den = _dot(ab, ab)
    if den == 0.0:
        return _dot(ap, ap)
    t = _dot(ap, ab) / den
    if t <= 0.0:
        return _dot(ap, ap)
    if t >= 1.0:
        bp = _sub(p, b)
        return _dot(bp, bp)
    q = (a[0] + t * ab[0] - p[0], a[1] + t * ab[1] - p[1])
    return _dot(q, q)


def segments_intersect(a: FPt, b: FPt, c: FPt, d: FPt) -> bool:
    """True when the closed segments ab and cd share at least one point (touching counts)."""
    eps2 = EPS * EPS
    return (point_segment_dist2(c, a, b) <= eps2 or point_segment_dist2(d, a, b) <= eps2
            or point_segment_dist2(a, c, d) <= eps2 or point_segment_dist2(b, c, d) <= eps2
            or _proper_cross(a, b, c, d))


def _proper_cross(a: FPt, b: FPt, c: FPt, d: FPt) -> bool:
    d1 = _cross(_sub(b, a), _sub(c, a))
    d2 = _cross(_sub(b, a), _sub(d, a))
    d3 = _cross(_sub(d, c), _sub(a, c))
    d4 = _cross(_sub(d, c), _sub(b, c))
    return ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4))


def segment_segment_dist2(a: FPt, b: FPt, c: FPt, d: FPt) -> float:
    """Squared distance between the closed segments ab and cd (0 when they meet)."""
    if _proper_cross(a, b, c, d):
        return 0.0
    return min(point_segment_dist2(a, c, d), point_segment_dist2(b, c, d),
               point_segment_dist2(c, a, b), point_segment_dist2(d, a, b))


def boundary_dist2(p: FPt, poly: Poly) -> float:
    """Squared distance from p to the polygon's boundary."""
    return min(point_segment_dist2(p, a, b) for a, b in edges(poly))


def segment_boundary_dist2(a: FPt, b: FPt, poly: Poly) -> float:
    """Squared distance from the segment ab to the polygon's boundary."""
    return min(segment_segment_dist2(a, b, c, d) for c, d in edges(poly))


def on_boundary(p: FPt, poly: Poly) -> bool:
    return boundary_dist2(p, poly) <= EPS * EPS


def point_in_polygon(p: FPt, poly: Poly) -> bool:
    """Closed point-in-polygon: boundary points are inside. Crossing number for the interior."""
    if on_boundary(p, poly):
        return True
    x, y = p
    inside = False
    for (x1, y1), (x2, y2) in edges(poly):
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                inside = not inside
    return inside


def point_strictly_inside(p: FPt, poly: Poly) -> bool:
    """Open point-in-polygon: boundary points are outside."""
    return not on_boundary(p, poly) and point_in_polygon(p, poly)


def clearance_ok(d2: float, margin: float) -> bool:
    """Distance (given squared) >= margin, allowing EPS: a point exactly at the margin passes."""
    m = margin - EPS
    return m <= 0.0 or d2 >= m * m


def _crossing_params(a: FPt, b: FPt, poly: Poly) -> list[float]:
    """Parameters t in [0, 1] where the segment a + t (b - a) meets the polygon boundary."""
    r = _sub(b, a)
    rr = _dot(r, r)
    ts = [0.0, 1.0]
    if rr == 0.0:
        return ts
    for c, d in edges(poly):
        s = _sub(d, c)
        den = _cross(r, s)
        qp = _sub(c, a)
        if den != 0.0:
            t = _cross(qp, s) / den
            u = _cross(qp, r) / den
            if -1e-12 <= t <= 1 + 1e-12 and -1e-12 <= u <= 1 + 1e-12:
                ts.append(min(1.0, max(0.0, t)))
        elif abs(_cross(qp, r)) <= EPS * EPS:   # collinear: the overlap's ends
            for e in (c, d):
                t = _dot(_sub(e, a), r) / rr
                if 0.0 <= t <= 1.0:
                    ts.append(t)
    return sorted(set(ts))


def segment_pieces(a: FPt, b: FPt, poly: Poly) -> list[FPt]:
    """Midpoints of the pieces of ab between consecutive boundary crossings (one per piece)."""
    ts = _crossing_params(a, b, poly)
    out: list[FPt] = []
    for t0, t1 in zip(ts, ts[1:], strict=False):
        t = (t0 + t1) / 2
        out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    return out


def segment_inside(a: FPt, b: FPt, poly: Poly) -> bool:
    """True when every point of the closed segment ab lies in the closed polygon."""
    if not (point_in_polygon(a, poly) and point_in_polygon(b, poly)):
        return False
    return all(point_in_polygon(m, poly) for m in segment_pieces(a, b, poly))


def segment_enters_interior(a: FPt, b: FPt, poly: Poly) -> bool:
    """True when some point of ab lies strictly inside the polygon (touching the boundary does not count)."""
    if point_strictly_inside(a, poly) or point_strictly_inside(b, poly):
        return True
    return any(point_strictly_inside(m, poly) for m in segment_pieces(a, b, poly))


def segment_meets_polygon(a: FPt, b: FPt, poly: Poly) -> bool:
    """True when the closed segment ab shares any point with the closed polygon (inside, on or crossing)."""
    if point_in_polygon(a, poly) or point_in_polygon(b, poly):
        return True
    return any(segments_intersect(a, b, c, d) for c, d in edges(poly))
