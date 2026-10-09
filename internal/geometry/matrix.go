package geometry

import "math"

type Vec4 [4]float64
type Mat4 [16]float64

func Identity() Mat4 { return Mat4{1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1} }

func Mul(left, right Mat4) (product Mat4) {
	for col := 0; col < 4; col++ {
		for row := 0; row < 4; row++ {
			for inner := 0; inner < 4; inner++ {
				product[col*4+row] += left[inner*4+row] * right[col*4+inner]
			}
		}
	}
	return
}

func Transform(matrix Mat4, point Vec4) (result Vec4) {
	for row := range result {
		for col := range point {
			result[row] += matrix[col*4+row] * point[col]
		}
	}
	return
}

func Translation(horizontal, vertical, depth float64) Mat4 {
	matrix := Identity()
	matrix[12], matrix[13], matrix[14] = horizontal, vertical, depth
	return matrix
}

func Scale(horizontal, vertical, depth float64) Mat4 {
	matrix := Identity()
	matrix[0], matrix[5], matrix[10] = horizontal, vertical, depth
	return matrix
}

func Rotation(angles [3]float64) Mat4 {
	xAngle, yAngle, zAngle := angles[0]*math.Pi/180, angles[1]*math.Pi/180, angles[2]*math.Pi/180
	xSin, xCos := math.Sincos(xAngle)
	ySin, yCos := math.Sincos(yAngle)
	zSin, zCos := math.Sincos(zAngle)
	xRotation := Mat4{1, 0, 0, 0, 0, xCos, xSin, 0, 0, -xSin, xCos, 0, 0, 0, 0, 1}
	yRotation := Mat4{yCos, 0, -ySin, 0, 0, 1, 0, 0, ySin, 0, yCos, 0, 0, 0, 0, 1}
	zRotation := Mat4{zCos, zSin, 0, 0, -zSin, zCos, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1}
	return Mul(Mul(xRotation, yRotation), zRotation)
}

func Compose(position, angles, scale [3]float64) Mat4 {
	return Mul(Mul(Translation(position[0], position[1], position[2]), Rotation(angles)), Scale(scale[0], scale[1], scale[2]))
}

func Perspective(fov, aspect, near, far float64) Mat4 {
	focal := 1 / math.Tan(fov*math.Pi/360)
	return Mat4{focal / aspect, 0, 0, 0, 0, focal, 0, 0, 0, 0, -(far + near) / (far - near), -1, 0, 0, -2 * far * near / (far - near), 0}
}

func Ortho(left, right, bottom, top, near, far float64) Mat4 {
	return Mat4{2 / (right - left), 0, 0, 0, 0, 2 / (top - bottom), 0, 0, 0, 0, -2 / (far - near), 0, -(right + left) / (right - left), -(top + bottom) / (top - bottom), -(far + near) / (far - near), 1}
}

func Clip(start, end Vec4) (Vec4, Vec4, bool) {
	lower, upper := 0.0, 1.0
	for axis := 0; axis < 3; axis++ {
		for _, sign := range []float64{-1, 1} {
			first, last := start[3]+sign*start[axis], end[3]+sign*end[axis]
			if first < 0 && last < 0 {
				return Vec4{}, Vec4{}, false
			}
			if first < 0 {
				lower = math.Max(lower, first/(first-last))
			} else if last < 0 {
				upper = math.Min(upper, first/(first-last))
			}
		}
	}
	if lower > upper {
		return Vec4{}, Vec4{}, false
	}
	var clippedStart, clippedEnd Vec4
	for axis := range start {
		clippedStart[axis] = start[axis] + lower*(end[axis]-start[axis])
		clippedEnd[axis] = start[axis] + upper*(end[axis]-start[axis])
	}
	return clippedStart, clippedEnd, clippedStart[3] > 0 && clippedEnd[3] > 0
}

func Viewport(point Vec4, width, height float64) (float64, float64) {
	return (point[0]/point[3] + 1) * width / 2, (1 - point[1]/point[3]) * height / 2
}
