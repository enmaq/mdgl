"""Column-major 4x4 matrices (right-handed GL conventions, SPEC "GL conventions")."""
import math


def identity():
    return [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def mul(left, right):
    product = [0.0] * 16
    for col in range(4):
        for row in range(4):
            for inner in range(4):
                product[col * 4 + row] += left[inner * 4 + row] * right[col * 4 + inner]
    return product


def transform(matrix, point):
    out = [0.0] * 4
    for row in range(4):
        for col in range(4):
            out[row] += matrix[col * 4 + row] * point[col]
    return out


def translation(x, y, z):
    m = identity()
    m[12], m[13], m[14] = x, y, z
    return m


def scaling(x, y, z):
    m = identity()
    m[0], m[5], m[10] = x, y, z
    return m


def rotation(angles):
    xa, ya, za = (a * math.pi / 180 for a in angles)
    xs, xc, ys, yc, zs, zc = math.sin(xa), math.cos(xa), math.sin(ya), math.cos(ya), math.sin(za), math.cos(za)
    rx = [1, 0, 0, 0, 0, xc, xs, 0, 0, -xs, xc, 0, 0, 0, 0, 1]
    ry = [yc, 0, -ys, 0, 0, 1, 0, 0, ys, 0, yc, 0, 0, 0, 0, 1]
    rz = [zc, zs, 0, 0, -zs, zc, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    return mul(mul(rx, ry), rz)


def compose(position, angles, scale):
    return mul(mul(translation(*position), rotation(angles)), scaling(*scale))


def perspective(fov, aspect, near, far):
    f = 1 / math.tan(fov * math.pi / 360)
    return [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, -(far + near) / (far - near), -1,
            0, 0, -2 * far * near / (far - near), 0]


def ortho(left, right, bottom, top, near, far):
    return [2 / (right - left), 0, 0, 0, 0, 2 / (top - bottom), 0, 0, 0, 0, -2 / (far - near), 0,
            -(right + left) / (right - left), -(top + bottom) / (top - bottom), -(far + near) / (far - near), 1]


def clip(start, end):
    """Clip a homogeneous segment against the six GL planes; returns (start, end) or None."""
    lower, upper = 0.0, 1.0
    for axis in range(3):
        for sign in (-1.0, 1.0):
            first, last = start[3] + sign * start[axis], end[3] + sign * end[axis]
            if first < 0 and last < 0:
                return None
            if first < 0:
                lower = max(lower, first / (first - last))
            elif last < 0:
                upper = min(upper, first / (first - last))
    if lower > upper:
        return None
    s = [start[a] + lower * (end[a] - start[a]) for a in range(4)]
    e = [start[a] + upper * (end[a] - start[a]) for a in range(4)]
    if s[3] > 0 and e[3] > 0:
        return s, e
    return None


def viewport(point, width, height):
    return (point[0] / point[3] + 1) * width / 2, (1 - point[1] / point[3]) * height / 2
