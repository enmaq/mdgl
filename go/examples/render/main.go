// Command render shows the public mdgl API: Parse, Frame, FallbackFrame, Active.
package main

import (
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"

	mdgl "github.com/enmaq/mdgl/go"
)

const invalidSource = "scene width=20 height=3 period=2s repeat=infinite fallback=end\nactor a = text(\"hi\") at (1, 1)\n@0: b.type()\n"

func main() {
	file := flag.String("f", "../examples/text.mdgl", "MDGL source file")
	at := flag.String("t", "4", "second to render, e.g. 0.5 or 0.5s")
	fallback := flag.Bool("fallback", false, "also print the fallback frame")
	color := flag.Bool("color", false, "emit ANSI foreground colours")
	invalid := flag.Bool("invalid", false, "parse a built-in invalid source and print its first diagnostic")
	flag.Parse()

	source := invalidSource
	if !*invalid {
		data, err := os.ReadFile(*file)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		source = string(data)
	}
	scene, diags := mdgl.Parse(source)
	if len(diags) > 0 {
		fmt.Fprintln(os.Stderr, "invalid MDGL:", diags[0].Error())
		if *invalid {
			return // demonstration only
		}
		os.Exit(1)
	}
	t, err := strconv.ParseFloat(strings.TrimSuffix(strings.TrimSpace(*at), "s"), 64)
	if err != nil || t < 0 || t != t || t > 1e12 {
		fmt.Fprintf(os.Stderr, "invalid time %q\n", *at)
		os.Exit(1)
	}
	for _, seconds := range []float64{t, 0} {
		fmt.Printf("@%g (%s)\n", seconds, state(scene, seconds))
		show(scene.Frame(seconds, scene.Width, scene.Height), *color)
	}
	if *fallback {
		fmt.Println("fallback")
		show(scene.FallbackFrame(scene.Width, scene.Height), *color)
	}
}

func state(scene *mdgl.Scene, t float64) string {
	if scene.Active(t) {
		return "active"
	}
	return "done"
}

func show(grid mdgl.Cells, color bool) {
	for _, row := range grid {
		var line strings.Builder
		for _, cell := range row {
			if color && cell.Color != "" && cell.Color != "normal" {
				fmt.Fprintf(&line, "\x1b[%dm%c\x1b[0m", ansi(cell.Color), cell.Rune)
			} else {
				line.WriteRune(cell.Rune)
			}
		}
		fmt.Println(strings.TrimRight(line.String(), " "))
	}
}

func ansi(name string) int {
	codes := map[string]int{"black": 30, "red": 31, "green": 32, "yellow": 33, "blue": 34, "magenta": 35, "cyan": 36, "accent": 36, "white": 37}
	if code, ok := codes[name]; ok {
		return code
	}
	return 39
}
