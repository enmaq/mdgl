package model

import (
	"fmt"
	"math"
	"unicode"

	"github.com/enmaq/mdgl/internal/geometry"
	"github.com/rivo/uniseg"
)

type Pos struct{ Line, Col int }

func (pos Pos) Error(message string) error {
	return fmt.Errorf("%d:%d: %s", pos.Line, pos.Col, message)
}

type Value struct {
	Text   string
	Pair   []Value
	Quoted bool
}
type Args map[string]Value
type Scene struct {
	Pos                Pos
	Attr               Args
	Actors             []Actor
	Actions            []Action
	Width, Height, FPS int
	Period             float64
	ExplicitPeriod     bool
	Repeat             int
	Fallback           string
}
type Actor struct {
	Pos                 Pos
	Name, Kind          string
	Args                Args
	X, Y                Value
	Attr                Args
	Text, Color, Parent string
	Width, Height       float64
	Z                   float64
	Rotation            [3]float64
	Scale               float64
	Material            string
}
type Action struct {
	Pos             Pos
	Actor, Verb     string
	Args            Args
	Begin, Duration float64
	Property, Ease  string
}
type ActorState struct {
	Actor                           Actor
	X, Y, Z, Scale, Opacity, Reveal float64
	Rotation                        [3]float64
	Transform                       geometry.Mat4
	Color                           string
}
type State struct {
	Width, Height int
	Actors        []ActorState
	Done          bool
}

func Glyphs(text string) []rune {
	result := []rune{}
	clusters := uniseg.NewGraphemes(text)
	for clusters.Next() {
		glyph := ' '
		if clusters.Width() > 1 {
			glyph = '\uFFFD'
		} else {
			for _, candidate := range clusters.Runes() {
				if !unicode.IsMark(candidate) && candidate != '\u200d' {
					glyph = candidate
					break
				}
			}
		}
		result = append(result, glyph)
	}
	return result
}
func Finite(value float64) bool { return !math.IsNaN(value) && !math.IsInf(value, 0) }

func Time(value float64) float64 {
	if math.Abs(value) > 1e6 {
		return value
	}
	return math.Round(value*1e9) / 1e9
}
