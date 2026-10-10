//! Column-major 4x4 matrices acting on column vectors (SPEC GL conventions).
pub type Vec4 = [f64; 4];
pub type Mat4 = [f64; 16];

pub const IDENTITY: Mat4 = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.];

pub fn mul(l: &Mat4, r: &Mat4) -> Mat4 {
    let mut p = [0.0; 16];
    for c in 0..4 {
        for row in 0..4 {
            for k in 0..4 {
                p[c * 4 + row] += l[k * 4 + row] * r[c * 4 + k];
            }
        }
    }
    p
}

pub fn transform(m: &Mat4, v: Vec4) -> Vec4 {
    let mut o = [0.0; 4];
    for (row, out) in o.iter_mut().enumerate() {
        for (c, x) in v.iter().enumerate() {
            *out += m[c * 4 + row] * x;
        }
    }
    o
}

pub fn translation(x: f64, y: f64, z: f64) -> Mat4 {
    let mut m = IDENTITY;
    (m[12], m[13], m[14]) = (x, y, z);
    m
}

pub fn scaling(x: f64, y: f64, z: f64) -> Mat4 {
    let mut m = IDENTITY;
    (m[0], m[5], m[10]) = (x, y, z);
    m
}

/// Intrinsic XYZ Euler rotation `Rx*Ry*Rz`, angles in degrees.
pub fn rotation(deg: [f64; 3]) -> Mat4 {
    let [xs, xc] = [deg[0].to_radians().sin(), deg[0].to_radians().cos()];
    let [ys, yc] = [deg[1].to_radians().sin(), deg[1].to_radians().cos()];
    let [zs, zc] = [deg[2].to_radians().sin(), deg[2].to_radians().cos()];
    let rx = [1., 0., 0., 0., 0., xc, xs, 0., 0., -xs, xc, 0., 0., 0., 0., 1.];
    let ry = [yc, 0., -ys, 0., 0., 1., 0., 0., ys, 0., yc, 0., 0., 0., 0., 1.];
    let rz = [zc, zs, 0., 0., -zs, zc, 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.];
    mul(&mul(&rx, &ry), &rz)
}

/// `T * R * S`.
pub fn compose(pos: [f64; 3], deg: [f64; 3], scale: [f64; 3]) -> Mat4 {
    mul(&mul(&translation(pos[0], pos[1], pos[2]), &rotation(deg)), &scaling(scale[0], scale[1], scale[2]))
}

pub fn perspective(fov_deg: f64, aspect: f64, near: f64, far: f64) -> Mat4 {
    let q = 1.0 / (fov_deg * std::f64::consts::PI / 360.0).tan();
    [q / aspect, 0., 0., 0., 0., q, 0., 0., 0., 0., -(far + near) / (far - near), -1., 0., 0., -2. * far * near / (far - near), 0.]
}

pub fn ortho(l: f64, r: f64, b: f64, t: f64, n: f64, f: f64) -> Mat4 {
    [2. / (r - l), 0., 0., 0., 0., 2. / (t - b), 0., 0., 0., 0., -2. / (f - n), 0., -(r + l) / (r - l), -(t + b) / (t - b), -(f + n) / (f - n), 1.]
}

/// Clip a segment against the six homogeneous planes `-w<=x,y,z<=w` before the divide.
pub fn clip(a: Vec4, b: Vec4) -> Option<(Vec4, Vec4)> {
    let (mut lo, mut hi) = (0.0f64, 1.0f64);
    for axis in 0..3 {
        for sign in [-1.0, 1.0] {
            let (first, last) = (a[3] + sign * a[axis], b[3] + sign * b[axis]);
            if first < 0.0 && last < 0.0 {
                return None;
            }
            if first < 0.0 {
                lo = lo.max(first / (first - last));
            } else if last < 0.0 {
                hi = hi.min(first / (first - last));
            }
        }
    }
    if lo > hi {
        return None;
    }
    let (mut s, mut e) = ([0.0; 4], [0.0; 4]);
    for i in 0..4 {
        s[i] = a[i] + lo * (b[i] - a[i]);
        e[i] = a[i] + hi * (b[i] - a[i]);
    }
    (s[3] > 0.0 && e[3] > 0.0).then_some((s, e))
}

pub fn viewport(p: Vec4, w: f64, h: f64) -> (f64, f64) {
    ((p[0] / p[3] + 1.0) * w / 2.0, (1.0 - p[1] / p[3]) * h / 2.0)
}
