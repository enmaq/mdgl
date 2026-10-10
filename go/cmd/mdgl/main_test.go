package main

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/enmaq/mdgl/go"
)

func TestRGBANSI(t *testing.T) {
	for _, sample := range []struct {
		color      string
		background bool
		want       string
	}{
		{"#800000", false, "\x1b[38;2;128;0;0m"},
		{"#123456", true, "\x1b[48;2;18;52;86m"},
		{"", true, "\x1b[40m"},
		{"red", false, "\x1b[31m"},
	} {
		if got := ansiColor(sample.color, sample.background); got != sample.want {
			t.Fatalf("ansi=%q want%q", got, sample.want)
		}
	}
}

func TestCLI(t *testing.T) {
	file := filepath.Join(t.TempDir(), "scene.mdgl")
	source := "scene width=4 height=1 fallback=end\nactor a = text(\"A\") at (0,0)\n@0: a.move(to=(3,0),dur=1)\n"
	if err := os.WriteFile(file, []byte(source), 0600); err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		args []string
		want string
	}{{[]string{"check", file}, "OK MDGL 0.1\n"}, {[]string{"frames", file, "--at", "0,1"}, "@0\nA   \n@1\n   A\n"}, {[]string{"play", file}, "   A\n"}} {
		var output bytes.Buffer
		if err := run(test.args, &output); err != nil {
			t.Fatal(err)
		}
		if output.String() != test.want {
			t.Fatalf("%v: %q", test.args, output.String())
		}
	}
	var output bytes.Buffer
	if err := run([]string{"frames", file, "--at", "NaN"}, &output); err == nil {
		t.Fatal("NaN accepted")
	}
}
func TestDirtyAndDone(t *testing.T) {
	scene, diags := mdgl.Parse("scene width=4 height=1 fallback=end\nactor a = text(\"A\") at (0,0)\n@0: a.move(to=(3,0),dur=1)\n")
	if len(diags) > 0 {
		t.Fatal(diags)
	}
	var output bytes.Buffer
	initial := scene.Frame(0, 4, 1)
	if err := dirty(&output, initial, initial); err != nil || output.Len() != 0 {
		t.Fatal("unchanged cells written")
	}
	start := time.Unix(0, 0)
	ticks := make(chan time.Time, 2)
	ticks <- start.Add(time.Second)
	ticks <- start.Add(2 * time.Second)
	if err := animate(context.Background(), &output, scene, start, ticks, initial); err != nil {
		t.Fatal(err)
	}
	if len(ticks) != 1 {
		t.Fatal("consumed ticks after completion")
	}
	if !strings.Contains(output.String(), "\x1b[?2026h") || !strings.HasSuffix(output.String(), "\x1b[?2026l") {
		t.Fatal("DEC 2026 framing")
	}
}
