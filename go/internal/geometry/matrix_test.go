package geometry

import (
	"math"
	"math/rand"
	"testing"
)

func closeVector(t *testing.T, got, want Vec4) {
	t.Helper()
	for axis := range got {
		if math.Abs(got[axis]-want[axis]) > 1e-9 {
			t.Fatalf("got %v want %v", got, want)
		}
	}
}

func TestRotationReferences(t *testing.T) {
	const diagonal = 0.7071067811865475244
	for _, sample := range []struct {
		angles      [3]float64
		input, want Vec4
	}{
		{[3]float64{90, 0, 0}, Vec4{0, 1, 0, 1}, Vec4{0, 0, 1, 1}},
		{[3]float64{45, 0, 0}, Vec4{0, 1, 0, 1}, Vec4{0, diagonal, diagonal, 1}},
		{[3]float64{0, 90, 0}, Vec4{1, 0, 0, 1}, Vec4{0, 0, -1, 1}},
		{[3]float64{0, 45, 0}, Vec4{1, 0, 0, 1}, Vec4{diagonal, 0, -diagonal, 1}},
		{[3]float64{0, 0, 90}, Vec4{1, 0, 0, 1}, Vec4{0, 1, 0, 1}},
		{[3]float64{0, 0, 45}, Vec4{1, 0, 0, 1}, Vec4{diagonal, diagonal, 0, 1}},
		{[3]float64{90, 90, 0}, Vec4{1, 0, 0, 1}, Vec4{0, 1, 0, 1}},
	} {
		closeVector(t, Transform(Rotation(sample.angles), sample.input), sample.want)
	}
}

func TestComposeReferences(t *testing.T) {
	matrix := Compose([3]float64{10, 20, 30}, [3]float64{0, 0, 90}, [3]float64{2, 3, 4})
	closeVector(t, Transform(matrix, Vec4{1, 2, 3, 1}), Vec4{4, 22, 42, 1})
	closeVector(t, Transform(matrix, Vec4{1, 2, 3, 0}), Vec4{-6, 2, 12, 0})
}

func TestProjectionReferences(t *testing.T) {
	perspective := Perspective(90, 2, 1, 9)
	wantPerspective := Mat4{0.5, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1.25, -1, 0, 0, -2.25, 0}
	for index := range perspective {
		if math.Abs(perspective[index]-wantPerspective[index]) > 1e-9 {
			t.Fatalf("perspective[%d]=%g", index, perspective[index])
		}
	}
	closeVector(t, Transform(perspective, Vec4{2, 1, -1, 1}), Vec4{1, 1, -1, 1})
	closeVector(t, Transform(perspective, Vec4{0, 0, -9, 1}), Vec4{0, 0, 9, 9})
	ortho := Ortho(-2, 6, -4, 4, 1, 9)
	wantOrtho := Mat4{.25, 0, 0, 0, 0, .25, 0, 0, 0, 0, -.25, 0, -.5, 0, -1.25, 1}
	if ortho != wantOrtho {
		t.Fatalf("ortho=%v", ortho)
	}
	closeVector(t, Transform(ortho, Vec4{2, 0, -1, 1}), Vec4{0, 0, -1, 1})
	closeVector(t, Transform(ortho, Vec4{6, 4, -9, 1}), Vec4{1, 1, 1, 1})
	horizontal, vertical := Viewport(Vec4{0, 1, 0, 1}, 80, 24)
	if horizontal != 40 || vertical != 0 {
		t.Fatalf("Y flip=%g,%g", horizontal, vertical)
	}
}

func TestRotationAndProjectionProperties(t *testing.T) {
	random := rand.New(rand.NewSource(19))
	for sample := 0; sample < 100; sample++ {
		point := Vec4{random.Float64()*20 - 10, random.Float64()*20 - 10, random.Float64()*20 - 10, 1}
		for axis := 0; axis < 3; axis++ {
			angles := [3]float64{}
			angles[axis] = 360
			closeVector(t, Transform(Rotation(angles), point), point)
			angles[axis] = random.Float64()*720 - 360
			forward := Rotation(angles)
			angles[axis] = -angles[axis]
			closeVector(t, Transform(Mul(Rotation(angles), forward), point), point)
		}
		near := .01 + random.Float64()*10
		projected := Transform(Perspective(10+random.Float64()*140, .2+random.Float64()*4, near, near+100), Vec4{0, 0, -near, 1})
		horizontal, vertical := Viewport(projected, 80, 24)
		if math.Abs(horizontal-40) > 1e-9 || math.Abs(vertical-12) > 1e-9 || math.Abs(projected[2]/projected[3]+1) > 1e-9 {
			t.Fatalf("near=%v", projected)
		}
	}
}

func TestClipNearPlane(t *testing.T) {
	projection := Perspective(90, 1, 1, 9)
	start, end, visible := Clip(Transform(projection, Vec4{0, 0, -.5, 1}), Transform(projection, Vec4{0, 0, -2, 1}))
	if !visible {
		t.Fatal("crossing edge rejected")
	}
	closeVector(t, start, Vec4{0, 0, -1, 1})
	closeVector(t, end, Vec4{0, 0, .25, 2})
	if _, _, visible := Clip(Transform(projection, Vec4{0, 0, 1, 1}), Transform(projection, Vec4{0, 0, 2, 1})); visible {
		t.Fatal("behind camera edge accepted")
	}
	for axis := 0; axis < 3; axis++ {
		for _, sign := range []float64{-1, 1} {
			outside := Vec4{0, 0, 0, 1}
			outside[axis] = 2 * sign
			clipped, _, ok := Clip(outside, Vec4{0, 0, 0, 1})
			if !ok || math.Abs(clipped[axis]-sign) > 1e-9 {
				t.Fatalf("plane %d %g: %v %v", axis, sign, clipped, ok)
			}
		}
	}
}
