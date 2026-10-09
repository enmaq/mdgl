package cells

import (
	"fmt"
	"math"
	"strconv"
)

func rgb(color string, background bool) [3]float64 {
	palette := map[string]uint32{"black": 0x000000, "red": 0xff0000, "green": 0x00ff00, "yellow": 0xffff00, "blue": 0x0000ff, "magenta": 0xff00ff, "cyan": 0x00ffff, "accent": 0x00ffff, "white": 0xffffff}
	value, found := palette[color]
	if len(color) == 7 && color[0] == '#' {
		parsed, err := strconv.ParseUint(color[1:], 16, 24)
		if err == nil {
			value, found = uint32(parsed), true
		}
	}
	if !found && !background {
		value = 0xffffff
	}
	return [3]float64{float64(value >> 16), float64(value >> 8 & 255), float64(value & 255)}
}

func overCell(destination Cell, glyph rune, color string, opacity float64) Cell {
	opacity = math.Max(0, math.Min(1, opacity))
	if opacity == 0 {
		return destination
	}
	if opacity == 1 {
		return Cell{Rune: glyph, Color: color, Background: destination.Background}
	}
	below := rgb(destination.Color, false)
	if destination.Rune == ' ' {
		below = rgb(destination.Background, true)
	}
	foreground := rgb(color, false)
	for component := range foreground {
		foreground[component] = math.Round(foreground[component]*opacity + below[component]*(1-opacity))
	}
	return Cell{Rune: glyph, Color: fmt.Sprintf("#%02x%02x%02x", int(foreground[0]), int(foreground[1]), int(foreground[2])), Background: destination.Background}
}
