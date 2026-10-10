package mdgl_test

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"github.com/enmaq/mdgl/go"
)

func TestConformance(t *testing.T) {
	paths, err := filepath.Glob("../conformance/*.mdgl")
	if err != nil {
		t.Fatal(err)
	}
	if len(paths) < 26 {
		t.Fatal("missing conformance cases")
	}
	for _, path := range paths {
		t.Run(strings.TrimSuffix(filepath.Base(path), ".mdgl"), func(t *testing.T) {
			source, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			scene, diags := mdgl.Parse(string(source))
			base := strings.TrimSuffix(path, ".mdgl")
			if expected, readErr := os.ReadFile(base + ".err"); readErr == nil {
				if len(diags) != 1 || diags[0].Error() != strings.TrimSpace(string(expected)) {
					t.Fatalf("want %q, got %v", strings.TrimSpace(string(expected)), diags)
				}
				return
			}
			if len(diags) != 0 {
				t.Fatal(diags)
			}
			expected, err := os.ReadFile(base + ".expect")
			if err != nil {
				t.Fatal(err)
			}
			lines := strings.Split(strings.TrimSuffix(string(expected), "\n"), "\n")
			for cursor := 0; cursor < len(lines); {
				marker := lines[cursor]
				cursor++
				if !strings.HasPrefix(marker, "@") {
					t.Fatalf("expected time marker: %q", marker)
				}
				seconds, err := strconv.ParseFloat(strings.TrimPrefix(marker, "@"), 64)
				if err != nil {
					t.Fatal(err)
				}
				rows := scene.Frame(seconds, scene.Width, scene.Height).Lines()
				for row := 0; row < scene.Height; row++ {
					if cursor >= len(lines) {
						t.Fatal("missing expected row")
					}
					want := lines[cursor]
					cursor++
					if len([]rune(want)) > scene.Width {
						t.Fatal("expected row exceeds stage")
					}
					want += strings.Repeat(" ", scene.Width-len([]rune(want)))
					if rows[row] != want {
						t.Errorf("at %g row %d: want %q, got %q", seconds, row, want, rows[row])
					}
				}
			}
		})
	}
}
