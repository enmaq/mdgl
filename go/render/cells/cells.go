package cells

import (
	"math"
	"sort"
	"strings"

	"github.com/enmaq/mdgl/go/internal/geometry"
	"github.com/enmaq/mdgl/go/model"
)

type Cell struct {
	Rune       rune
	Color      string
	Background string
}
type Cells [][]Cell

func (grid Cells) Lines() []string {
	rows := make([]string, len(grid))
	for row, line := range grid {
		var text strings.Builder
		for _, cell := range line {
			text.WriteRune(cell.Rune)
		}
		rows[row] = text.String()
	}
	return rows
}

func Render(state model.State, cols, rows int) Cells {
	cols = max(0, min(200, cols))
	rows = max(0, min(60, rows))
	grid := make(Cells, rows)
	for row := range grid {
		grid[row] = make([]Cell, cols)
		for col := range grid[row] {
			grid[row][col] = Cell{Rune: ' ', Color: "normal"}
		}
	}
	if rows == 0 || cols == 0 {
		return grid
	}
	actors := append([]model.ActorState(nil), state.Actors...)
	sort.SliceStable(actors, func(first, second int) bool { return actors[first].Z < actors[second].Z })
	for _, actor := range actors {
		if actor.Opacity <= 0 || actor.Reveal <= 0 {
			continue
		}
		if actor.Actor.Kind == "text" {
			paintText(grid, actor, actor.Actor.Text, 0, 0, actor.Actor.Width)
			continue
		}
		dots := make([][]bool, rows*4)
		for row := range dots {
			dots[row] = make([]bool, cols*2)
		}
		width, height := actor.Actor.Width, actor.Actor.Height
		originX, originY := 0.0, 0.0
		lastX, lastY := originX+math.Max(0, width*2-1), originY+math.Max(0, height*4-1)
		drawLine := func(startX, startY, endX, endY float64) {
			matrix := geometry.Mul(geometry.Ortho(0, float64(cols), -2*float64(rows), 0, -1000, 1000), actorTransform(actor))
			start := geometry.Transform(matrix, geometry.Vec4{startX / 2, -startY / 2, 0, 1})
			end := geometry.Transform(matrix, geometry.Vec4{endX / 2, -endY / 2, 0, 1})
			start, end, visible := geometry.Clip(start, end)
			if !visible {
				return
			}
			startX, startY = geometry.Viewport(start, float64(cols)*2, float64(rows)*4)
			endX, endY = geometry.Viewport(end, float64(cols)*2, float64(rows)*4)
			line(dots, startX, startY, endX, endY)
		}
		switch actor.Actor.Kind {
		case "rect":
			drawLine(originX, originY, lastX, originY)
			drawLine(lastX, originY, lastX, lastY)
			drawLine(lastX, lastY, originX, lastY)
			drawLine(originX, lastY, originX, originY)
		case "circle":
			centerX, centerY := (originX+lastX)/2, (originY+lastY)/2
			radiusX, radiusY := (lastX-originX)/2, (lastY-originY)/2
			previousX, previousY := centerX+radiusX, centerY
			for sample := 1; sample <= 720; sample++ {
				angle := float64(sample) * math.Pi / 360
				nextX, nextY := centerX+radiusX*math.Cos(angle), centerY+radiusY*math.Sin(angle)
				drawLine(previousX, previousY, nextX, nextY)
				previousX, previousY = nextX, nextY
			}
		case "cube":
			cube(dots, actor)
		}
		for row := range grid {
			for col := range grid[row] {
				mask := 0
				for vertical := 0; vertical < 4; vertical++ {
					for horizontal := 0; horizontal < 2; horizontal++ {
						if dots[row*4+vertical][col*2+horizontal] {
							bit := [4][2]int{{0, 3}, {1, 4}, {2, 5}, {6, 7}}[vertical][horizontal]
							mask |= 1 << bit
						}
					}
				}
				if mask != 0 && (actor.Reveal >= 1 || float64(col)+0.5 <= actor.X+width*actor.Scale*actor.Reveal) {
					grid[row][col] = overCell(grid[row][col], rune(0x2800+mask), actor.Color, actor.Opacity)
				}
			}
		}
		if actor.Actor.Kind == "rect" && actor.Actor.Text != "" {
			paintText(grid, actor, actor.Actor.Text, 1, 0, math.Max(0, actor.Actor.Width-2))
		}
	}
	return grid
}
func paintText(grid Cells, actor model.ActorState, text string, originX, originY, maxWidth float64) {
	glyphs := model.Glyphs(text)
	limit := min(len(glyphs), int(math.Floor(maxWidth*actor.Reveal+1e-9)))
	for index := 0; index < limit; index++ {
		point := geometry.Transform(actorTransform(actor), geometry.Vec4{originX + float64(index), -2 * originY, 0, 1})
		horizontal := math.Round(point[0])
		vertical := math.Round(-point[1] / 2)
		if horizontal < 0 || vertical < 0 || vertical >= float64(len(grid)) || horizontal >= float64(len(grid[0])) {
			continue
		}
		if glyphs[index] != ' ' {
			grid[int(vertical)][int(horizontal)] = overCell(grid[int(vertical)][int(horizontal)], glyphs[index], actor.Color, actor.Opacity)
		}
	}
}
func line(dots [][]bool, startX, startY, endX, endY float64) {
	startX, startY = math.Round(startX*1e9)/1e9, math.Round(startY*1e9)/1e9
	endX, endY = math.Round(endX*1e9)/1e9, math.Round(endY*1e9)/1e9
	width, height := float64(len(dots[0])-1), float64(len(dots)-1)
	deltaX, deltaY := endX-startX, endY-startY
	lower, upper := 0.0, 1.0
	for _, bound := range [][2]float64{{-deltaX, startX}, {deltaX, width - startX}, {-deltaY, startY}, {deltaY, height - startY}} {
		direction, distance := bound[0], bound[1]
		if direction == 0 {
			if distance < 0 {
				return
			}
			continue
		}
		ratio := distance / direction
		if direction < 0 {
			lower = math.Max(lower, ratio)
		} else {
			upper = math.Min(upper, ratio)
		}
		if lower > upper {
			return
		}
	}
	clippedX, clippedY := startX+lower*deltaX, startY+lower*deltaY
	endX, endY = startX+upper*deltaX, startY+upper*deltaY
	steps := int(math.Min(800, math.Ceil(math.Max(math.Abs(endX-clippedX), math.Abs(endY-clippedY)))))
	if steps <= 0 {
		steps = 1
	}
	for step := 0; step <= steps; step++ {
		progress := float64(step) / float64(steps)
		horizontal, vertical := int(math.Round(clippedX+(endX-clippedX)*progress)), int(math.Round(clippedY+(endY-clippedY)*progress))
		if vertical >= 0 && vertical < len(dots) && horizontal >= 0 && horizontal < len(dots[0]) {
			dots[vertical][horizontal] = true
		}
	}
}
func cube(dots [][]bool, actor model.ActorState) {
	cubeCamera(dots, actor, 3*actor.Actor.Width, 0.1, 1000)
}

func actorTransform(actor model.ActorState) geometry.Mat4 {
	if actor.Transform != (geometry.Mat4{}) {
		return actor.Transform
	}
	anchorX, anchorY := actor.Actor.Width/2, actor.Actor.Height
	return geometry.Mul(geometry.Compose([3]float64{actor.X + anchorX, -2*actor.Y - anchorY, 0}, actor.Rotation, [3]float64{actor.Scale, actor.Scale, actor.Scale}), geometry.Translation(-anchorX, anchorY, 0))
}

func cubeCamera(dots [][]bool, actor model.ActorState, distance, near, far float64) {
	size := actor.Actor.Width
	world := actorTransform(actor)
	center := geometry.Transform(world, geometry.Vec4{size / 2, -actor.Actor.Height, 0, 1})
	view := geometry.Translation(-center[0], -center[1], -distance)
	projection := geometry.Perspective(50, actor.Actor.Width/(2*actor.Actor.Height), near, far)
	matrix := geometry.Mul(geometry.Mul(projection, view), world)
	corners := [8]geometry.Vec4{}
	for index := 0; index < 8; index++ {
		horizontal, vertical, depth := -0.5, -0.5, -0.5
		if index&1 != 0 {
			horizontal = 0.5
		}
		if index&2 != 0 {
			vertical = 0.5
		}
		if index&4 != 0 {
			depth = 0.5
		}
		corners[index] = geometry.Transform(matrix, geometry.Vec4{size/2 + horizontal*size, -actor.Actor.Height + vertical*size, depth * size, 1})
	}
	for index := 0; index < 8; index++ {
		for _, bit := range []int{1, 2, 4} {
			other := index ^ bit
			if other > index {
				start, end, visible := geometry.Clip(corners[index], corners[other])
				if !visible {
					continue
				}
				startX, startY := geometry.Viewport(start, size, actor.Actor.Height)
				endX, endY := geometry.Viewport(end, size, actor.Actor.Height)
				originX, originY := center[0]-size/2, -center[1]/2-actor.Actor.Height/2
				line(dots, (originX+startX)*2-0.5, (originY+startY)*4-0.5, (originX+endX)*2-0.5, (originY+endY)*4-0.5)
			}
		}
	}
}
