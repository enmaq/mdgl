package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"time"

	"github.com/enmaq/mdgl/go"
)

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run(args []string, output io.Writer) error {
	if len(args) < 2 {
		return fmt.Errorf("usage: mdgl check FILE | frames FILE --at t1,t2 | play FILE")
	}
	command, file := args[0], args[1]
	if command != "check" && command != "frames" && command != "play" {
		return fmt.Errorf("unknown command %q", command)
	}
	options := flag.NewFlagSet(command, flag.ContinueOnError)
	options.SetOutput(io.Discard)
	times := options.String("at", "0", "comma-separated seconds")
	if err := options.Parse(args[2:]); err != nil {
		return err
	}
	if options.NArg() != 0 {
		return fmt.Errorf("unexpected arguments")
	}
	handle, err := os.Open(file)
	if err != nil {
		return err
	}
	source, readErr := io.ReadAll(io.LimitReader(handle, 256*1024+1))
	closeErr := handle.Close()
	if readErr != nil {
		return readErr
	}
	if closeErr != nil {
		return closeErr
	}
	scene, diags := mdgl.Parse(string(source))
	if len(diags) > 0 {
		return diags[0]
	}
	switch command {
	case "check":
		_, err = fmt.Fprintln(output, "OK MDGL 0.1")
		return err
	case "frames":
		samples := []float64{}
		for _, value := range strings.Split(*times, ",") {
			seconds, parseErr := strconv.ParseFloat(strings.TrimSuffix(strings.TrimSpace(value), "s"), 64)
			if parseErr != nil || seconds < 0 || seconds != seconds || seconds > 1e12 {
				return fmt.Errorf("invalid frame time %q", value)
			}
			samples = append(samples, seconds)
		}
		for _, seconds := range samples {
			if _, err = fmt.Fprintf(output, "@%g\n", seconds); err != nil {
				return err
			}
			if err = plain(output, scene.Frame(seconds, scene.Width, scene.Height)); err != nil {
				return err
			}
		}
		return nil
	case "play":
		terminal := false
		if handle, ok := output.(*os.File); ok {
			info, statErr := handle.Stat()
			terminal = statErr == nil && info.Mode()&os.ModeCharDevice != 0
		}
		if !terminal || os.Getenv("NO_COLOR") != "" || os.Getenv("MDGL_REDUCED_MOTION") != "" {
			return plain(output, scene.FallbackFrame(scene.Width, scene.Height))
		}
		ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
		defer stop()
		return play(ctx, output, scene)
	}
	return nil
}
func plain(output io.Writer, grid mdgl.Cells) error {
	for _, row := range grid.Lines() {
		if _, err := fmt.Fprintln(output, row); err != nil {
			return err
		}
	}
	return nil
}
func play(ctx context.Context, output io.Writer, scene *mdgl.Scene) error {
	if _, err := io.WriteString(output, "\x1b[?25l"); err != nil {
		return err
	}
	defer io.WriteString(output, "\x1b[?2026l\x1b[0m\x1b[?25h\n")
	previous := mdgl.Cells(nil)
	if err := dirty(output, previous, scene.Frame(0, scene.Width, scene.Height)); err != nil {
		return err
	}
	if !scene.Active(0) {
		return nil
	}
	start := time.Now()
	ticker := time.NewTicker(time.Second / time.Duration(scene.FPS))
	defer ticker.Stop()
	previous = scene.Frame(0, scene.Width, scene.Height)
	return animate(ctx, output, scene, start, ticker.C, previous)
}
func animate(ctx context.Context, output io.Writer, scene *mdgl.Scene, start time.Time, ticks <-chan time.Time, previous mdgl.Cells) error {
	for {
		select {
		case <-ctx.Done():
			return nil
		case instant, open := <-ticks:
			if !open {
				return nil
			}
			elapsed := instant.Sub(start).Seconds()
			current := scene.Frame(elapsed, scene.Width, scene.Height)
			if err := dirty(output, previous, current); err != nil {
				return err
			}
			previous = current
			if !scene.Active(elapsed) {
				return nil
			}
		}
	}
}
func dirty(output io.Writer, previous, current mdgl.Cells) error {
	var buffer strings.Builder
	for row, line := range current {
		for col, cell := range line {
			if row < len(previous) && col < len(previous[row]) && cell == previous[row][col] {
				continue
			}
			fmt.Fprintf(&buffer, "\x1b[%d;%dH%s%s%c", row+1, col+1, ansiColor(cell.Color, false), ansiColor(cell.Background, true), cell.Rune)
		}
	}
	if buffer.Len() == 0 {
		return nil
	}
	_, err := io.WriteString(output, "\x1b[?2026h"+buffer.String()+"\x1b[?2026l")
	return err
}

func ansiColor(color string, background bool) string {
	if background && (color == "" || color == "normal") {
		color = "black"
	}
	if len(color) == 7 && color[0] == '#' {
		value, err := strconv.ParseUint(color[1:], 16, 24)
		if err == nil {
			prefix := 38
			if background {
				prefix = 48
			}
			return fmt.Sprintf("\x1b[%d;2;%d;%d;%dm", prefix, value>>16, value>>8&255, value&255)
		}
	}
	code := colorCode(color)
	if background {
		code += 10
	}
	return fmt.Sprintf("\x1b[%dm", code)
}
func colorCode(color string) int {
	switch color {
	case "black":
		return 30
	case "red":
		return 31
	case "green":
		return 32
	case "yellow":
		return 33
	case "blue":
		return 34
	case "magenta":
		return 35
	case "cyan", "accent":
		return 36
	case "white":
		return 37
	}
	return 39
}
