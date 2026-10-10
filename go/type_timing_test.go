package mdgl_test

import "testing"

func TestTypeRevealUsesExactNanosecondBoundaries(t *testing.T) {
	scene := mustScene(t, "scene width=4 height=1 fallback=end\nactor a = text(\"ABC\") at (0,0)\n@0: a.type(per_char=1)\n")
	before := scene.Frame(0.999999999, 4, 1)[0]
	at := scene.Frame(1, 4, 1)[0]
	if before[0].Rune != ' ' {
		t.Fatalf("one ns before first type boundary revealed %q", before[0].Rune)
	}
	if at[0].Rune != 'A' {
		t.Fatalf("at first type boundary revealed %q", at[0].Rune)
	}

	tenths := mustScene(t, "scene width=4 height=1 fallback=end\nactor a = text(\"ABC\") at (0,0)\n@0: a.type(per_char=0.1)\n")
	justBefore := tenths.Frame(0.299999999, 4, 1)[0]
	atThird := tenths.Frame(0.3, 4, 1)[0]
	if justBefore[2].Rune != ' ' {
		t.Fatalf("one ns before 0.3 s revealed third glyph %q", justBefore[2].Rune)
	}
	if atThird[2].Rune != 'C' {
		t.Fatalf("at 0.3 s third glyph = %q", atThird[2].Rune)
	}
}
