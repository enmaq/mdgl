package mdgl_test

import (
	"math"
	"reflect"
	"strings"
	"sync"
	"testing"

	"github.com/enmaq/mdgl/go"
)

func mustScene(t *testing.T, source string) *mdgl.Scene {
	t.Helper()
	scene, diags := mdgl.Parse(source)
	if len(diags) > 0 {
		t.Fatal(diags)
	}
	return scene
}
func TestSeekingAndConcurrentFrames(t *testing.T) {
	scene := mustScene(t, "scene width=8 height=1 fallback=end\nactor a = text(\"AB\") at (0,0)\n@0: a.move(to=(6,0),dur=2)\n")
	expected := scene.Frame(1, 8, 1)
	scene.Frame(2, 8, 1)
	scene.Frame(0, 8, 1)
	if !reflect.DeepEqual(expected, scene.Frame(1, 8, 1)) {
		t.Fatal("seek depended on history")
	}
	var group sync.WaitGroup
	for index := 0; index < 8; index++ {
		group.Add(1)
		go func() {
			defer group.Done()
			if !reflect.DeepEqual(expected, scene.Frame(1, 8, 1)) {
				t.Error("concurrent frame differs")
			}
		}()
	}
	group.Wait()
	if scene.Active(2) || !scene.Active(1.99) {
		t.Fatal("active boundary")
	}
}
func TestFallbackInfiniteAndDimensions(t *testing.T) {
	scene := mustScene(t, "scene width=8 height=1 period=1 repeat=infinite fallback=end\nactor a = text(\"AB\") at (0,0)\n@0: a.move(to=(4,0),dur=1)\n")
	if !scene.Active(1000) {
		t.Fatal("infinite stopped")
	}
	if scene.FallbackFrame(8, 1).Lines()[0] != "    AB  " {
		t.Fatal("fallback end wrapped")
	}
	if scene.Frame(1, 8, 1).Lines()[0] != "AB      " {
		t.Fatal("repeat boundary did not reset")
	}
	if len(scene.Frame(0, 2, 1)[0]) != 2 || len(scene.Frame(0, -1, -1)) != 0 {
		t.Fatal("clip dimensions")
	}
	if scene.Active(math.NaN()) {
		t.Fatal("NaN active")
	}
}
func TestColorsEasingAndZ(t *testing.T) {
	scene := mustScene(t, "scene width=8 height=1 fallback=end\nactor a = text(\"A\") at (0,0) color=green z=2\nactor b = text(\"B\") at (0,0) z=1\n@0: a.color(to=red,dur=2,ease=ease-in)\n")
	if cell := scene.Frame(1, 8, 1)[0][0]; cell.Rune != 'A' || cell.Color != "green" {
		t.Fatalf("%+v", cell)
	}
	if scene.Frame(2, 8, 1)[0][0].Color != "red" {
		t.Fatal("color did not freeze")
	}
}
func TestInvalidInputs(t *testing.T) {
	cases := []string{
		"scene width=8 height=1 fallback=end fps=31",
		"scene width=8 height=1 fallback=end period=1\nactor a = text(\"A\") at (0,0)\n@0: a.fade(in,dur=2)",
		"scene width=8 height=1 fallback=end\nactor a = text(\"\\x1b[31m\") at (0,0)",
		"scene width=8 height=1 fallback=end\nactor a = text(\"A\") at (top,0)",
		"scene width=8 height=1 fallback=end\nactor a = cube(size=4,style=solid) at (0,0)",
		"scene width=8 height=1 fallback=end\nactor a = text(\"A\") at (0,0)\n@0: a.rotate(x=90,dur=1)",
		"scene width=8 height=1 fallback=end\nactor a = text(\"A\") at (0,0)\n@0: a.move(to=(0,0),dur=2)\n@1: a.slide(out,to=left,dur=1)",
		"scene width=8 height=1 fallback=end width=8",
		"scene width=8 height=1 fallback=end\nactor a = text(\"unterminated) at (0,0)",
		"scene width=8 height=1 fallback=end\nactor a = text(\"A\") at (0,0)\n@0: a.fade(in,dur=1,)",
		"scene width=8 height=1 fallback=@2",
	}
	for _, source := range cases {
		if scene, diags := mdgl.Parse(source); scene != nil || len(diags) == 0 {
			t.Errorf("accepted invalid: %s", source)
		}
	}
}
func TestResourceLimits(t *testing.T) {
	if _, diags := mdgl.Parse(strings.Repeat(" ", 256*1024+1)); len(diags) == 0 {
		t.Fatal("input limit")
	}
	source := "scene width=1 height=1 fallback=end\n"
	for index := 0; index < 65; index++ {
		source += "actor a" + strings.Repeat("a", index) + " = text(\"A\") at (0,0)\n"
	}
	if _, diags := mdgl.Parse(source); len(diags) == 0 {
		t.Fatal("actor limit")
	}
}

func TestShapesAndReservedVocabulary(t *testing.T) {
	for _, kind := range []string{"rect(2,1)", "circle(1)", "cube(size=4)"} {
		scene := mustScene(t, "scene width=8 height=4 fallback=end\nactor a = "+kind+" at (0,0) color=cyan\n")
		count := 0
		for _, row := range scene.Frame(0, 8, 4) {
			for _, cell := range row {
				if cell.Rune != ' ' {
					count++
					if cell.Rune < 0x2801 || cell.Rune > 0x28ff || cell.Color != "cyan" {
						t.Fatalf("invalid shape cell: %+v", cell)
					}
				}
			}
		}
		if count == 0 {
			t.Fatalf("empty %s", kind)
		}
	}
	for _, statement := range []string{"camera orthographic", "light ambient(intensity=1)", "actor a = threejs(\"scene.json\") at (0,0)", "actor a = text(\"A\") at (0,0) material=basic"} {
		_, diags := mdgl.Parse("scene width=8 height=4 fallback=end\n" + statement + "\n")
		if len(diags) != 1 || !strings.Contains(diags[0].Message, "reserved; not yet supported in 0.1") {
			t.Fatalf("reserved %q: %v", statement, diags)
		}
	}
}

func TestDelayedVisibilityAndParentScale(t *testing.T) {
	scene := mustScene(t, "scene width=8 height=1 fallback=end\nactor p = text(\"\") at (1,0) anchor=(0,0)\nactor a = text(\"AB\") at (1,0) parent=p\n@0: p.scale(to=2,dur=1)\n@1: a.fade(in,dur=1)\n")
	if strings.TrimSpace(scene.Frame(0, 8, 1).Lines()[0]) != "" {
		t.Fatal("fade-in visible before begin")
	}
	if scene.Frame(2, 8, 1).Lines()[0] != "   A B  " {
		t.Fatal("parent scale/translation did not compose")
	}
}

func TestDecimalTimingBoundaries(t *testing.T) {
	scene := mustScene(t, "scene width=8 height=1 period=0.5 fallback=end\nactor a = text(\"A\") at (0,0)\n@0.1: a.move(to=(2,0),dur=0.2)\n@0.3: a.move(to=(4,0),dur=0.2)\n")
	if scene.Frame(0.3, 8, 1).Lines()[0] != "  A     " {
		t.Fatal("adjacent decimal boundary")
	}
	loop := mustScene(t, "scene width=8 height=1 period=0.1 repeat=infinite fallback=end\nactor a = text(\"A\") at (0,0)\n@0: a.move(to=(4,0),dur=0.1)\n")
	if loop.Frame(0.3, 8, 1).Lines()[0] != "A       " {
		t.Fatal("decimal repeat boundary")
	}
	finite := mustScene(t, "scene width=8 height=1 period=0.1 repeat=3 fallback=end\n")
	if finite.Active(0.3) {
		t.Fatal("decimal finite end still active")
	}
}

func TestQuotedTokensRemainText(t *testing.T) {
	for _, text := range []string{")", "<end>", "(", "scene", "="} {
		scene := mustScene(t, "scene width=8 height=1 fallback=end\nactor a = text(\""+text+"\") at (0,0)\n")
		if strings.TrimSpace(scene.Frame(0, 8, 1).Lines()[0]) != text {
			t.Fatalf("text %q lost", text)
		}
	}
	for _, source := range []string{
		"\"scene\" width=8 height=1 fallback=end",
		"scene \"width\"=8 height=1 fallback=end",
		"scene width=8 height=1 fallback=end\nactor \"a\" = text(\"A\") at (0,0)",
		"scene width=8 height=1 fallback=end\nactor a = text(\"A\") at (0,0)\n@\"0\": a.fade(in,dur=1)",
		"scene width=8 height=1 fallback=end\nactor a = text(\"A\") at (0,0)\n@0: a.fade(in,\"dur\"=1)",
	} {
		if _, diags := mdgl.Parse(source); len(diags) == 0 {
			t.Fatalf("accepted quoted syntax %q", source)
		}
	}
}
