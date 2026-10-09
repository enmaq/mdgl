package eval

import (
	"github.com/enmaq/mdgl/check"
	"github.com/enmaq/mdgl/internal/geometry"
	"github.com/enmaq/mdgl/parse"
	"math"
	"testing"
)

func TestSceneGraphTransformAndOpacity(t *testing.T) {
	scene, err := parse.Parse("scene width=40 height=20 fallback=end\nactor p = cube(size=4) at (10,5)\nactor c = text(\"C\") at (3,1) parent=p\n@0: p.rotate(z=90,dur=1)\n@0: p.scale(to=2,dur=1)\n@0: p.fade(out,dur=2)\n@0: c.fade(out,dur=2)\n")
	if err != nil {
		t.Fatal(err)
	}
	if err = check.Check(scene); err != nil {
		t.Fatal(err)
	}
	state := At(scene, 1)
	parent, child := state.Actors[0], state.Actors[1]
	point := geometry.Transform(child.Transform, geometry.Vec4{0, 0, 0, 1})
	if math.Abs(point[0]-8) > 1e-9 || math.Abs(point[1]+12) > 1e-9 {
		t.Fatalf("child world origin=%v", point)
	}
	if child.Opacity != .25 || parent.Opacity != .5 {
		t.Fatalf("opacity=%g,%g", parent.Opacity, child.Opacity)
	}
	center := geometry.Transform(parent.Transform, geometry.Vec4{2, -4, 0, 1})
	if math.Abs(center[0]-12) > 1e-9 || math.Abs(center[1]+14) > 1e-9 {
		t.Fatalf("parent pivot moved: %v", center)
	}
}

func TestExplicitAnchorAndRadians(t *testing.T) {
	scene, err := parse.Parse("scene width=20 height=10 fallback=end\nactor p = cube(size=4) at (5,2) anchor=(0,0)\n@0: p.scale(to=2,dur=1)\n@0: p.rotate(x=1.5707963267948966rad,y=90deg,dur=1)\n")
	if err != nil {
		t.Fatal(err)
	}
	if err = check.Check(scene); err != nil {
		t.Fatal(err)
	}
	actor := At(scene, 1).Actors[0]
	if math.Abs(actor.Rotation[0]-90) > 1e-9 || actor.Rotation[1] != 90 {
		t.Fatalf("rotation=%v", actor.Rotation)
	}
	origin := geometry.Transform(actor.Transform, geometry.Vec4{0, 0, 0, 1})
	if origin != (geometry.Vec4{5, -4, 0, 1}) {
		t.Fatalf("anchor origin=%v", origin)
	}
}
