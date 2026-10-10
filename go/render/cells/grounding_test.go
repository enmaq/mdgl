package cells

import (
	"github.com/enmaq/mdgl/go/model"
	"testing"
)

func TestRGBSourceOver(t *testing.T) {
	for _, sample := range []struct {
		below   Cell
		opacity float64
		color   string
	}{
		{Cell{Rune: 'B', Color: "blue"}, .5, "#800080"},
		{Cell{Rune: ' ', Background: "white"}, .5, "#ff8080"},
		{Cell{Rune: 'B', Color: "blue"}, .25, "#4000bf"},
		{Cell{Rune: 'B', Color: "blue"}, 1, "red"},
	} {
		got := overCell(sample.below, 'R', "red", sample.opacity)
		if got.Color != sample.color || got.Background != sample.below.Background {
			t.Fatalf("blend=%+v want%s", got, sample.color)
		}
	}
	below := Cell{Rune: 'B', Color: "blue", Background: "white"}
	if overCell(below, 'R', "red", 0) != below {
		t.Fatal("zero alpha changed destination")
	}
	state := model.State{Actors: []model.ActorState{{Actor: model.Actor{Kind: "text", Text: "X", Width: 1, Height: 1}, Scale: 1, Opacity: .25, Reveal: 1, Color: "red"}}}
	grid := Render(state, 2, 2)
	if grid[0][0].Rune != 'X' || grid[0][0].Color != "#400000" {
		t.Fatalf("quarter-opacity text invisible: %+v", grid)
	}
}

func TestCubeCrossesNearPlane(t *testing.T) {
	dots := make([][]bool, 40)
	for row := range dots {
		dots[row] = make([]bool, 28)
	}
	actor := model.ActorState{Actor: model.Actor{Kind: "cube", Width: 8, Height: 8}, X: 3, Y: 1, Scale: 1, Opacity: 1, Reveal: 1, Rotation: [3]float64{30, 45, 0}}
	cubeCamera(dots, actor, 3, .1, 1000)
	painted := 0
	for _, row := range dots {
		for _, dot := range row {
			if dot {
				painted++
			}
		}
	}
	if painted == 0 {
		t.Fatal("clipped crossing cube entirely discarded")
	}
	for _, row := range dots {
		clear(row)
	}
	cubeCamera(dots, actor, -20, .1, 1000)
	for _, row := range dots {
		for _, dot := range row {
			if dot {
				t.Fatal("behind-camera cube painted")
			}
		}
	}
}
