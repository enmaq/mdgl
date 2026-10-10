package mdgl

import (
	"fmt"
	"strconv"
	"strings"

	"github.com/enmaq/mdgl/go/check"
	"github.com/enmaq/mdgl/go/eval"
	"github.com/enmaq/mdgl/go/model"
	"github.com/enmaq/mdgl/go/parse"
	"github.com/enmaq/mdgl/go/render/cells"
)

type Cell = cells.Cell
type Cells = cells.Cells
type Diag struct {
	Line, Col int
	Message   string
}

func (diag Diag) Error() string { return fmt.Sprintf("%d:%d: %s", diag.Line, diag.Col, diag.Message) }

type Scene struct {
	Period             float64
	Fallback           float64
	Width, Height, FPS int
	scene              *model.Scene
}

func Signatures() []string { return check.Signatures() }

func Parse(source string) (*Scene, []Diag) {
	parsed, err := parse.Parse(source)
	if err == nil {
		err = check.Check(parsed)
	}
	if err != nil {
		parts := strings.SplitN(err.Error(), ":", 3)
		diag := Diag{Line: 1, Col: 1, Message: err.Error()}
		if len(parts) == 3 {
			diag.Line, _ = strconv.Atoi(parts[0])
			diag.Col, _ = strconv.Atoi(parts[1])
			diag.Message = strings.TrimSpace(parts[2])
		}
		return nil, []Diag{diag}
	}
	fallback := 0.0
	if parsed.Fallback == "end" {
		fallback = parsed.Period
	} else if strings.HasPrefix(parsed.Fallback, "@") {
		fallback = check.Number(model.Value{Text: strings.TrimPrefix(parsed.Fallback, "@")})
	}
	return &Scene{Period: parsed.Period, Fallback: fallback, Width: parsed.Width, Height: parsed.Height, FPS: parsed.FPS, scene: parsed}, nil
}
func (scene *Scene) Frame(time float64, cols, rows int) Cells {
	frame, _ := scene.FrameWithDone(time, cols, rows)
	return frame
}

// FrameWithDone returns the rendered frame and the evaluator's completion
// state for the same absolute time. Frame remains the cells-only convenience
// API for existing callers.
func (scene *Scene) FrameWithDone(time float64, cols, rows int) (Cells, bool) {
	if scene == nil || scene.scene == nil {
		return nil, false
	}
	state := eval.Frame(scene.scene, time)
	return cells.Render(state, min(cols, scene.scene.Width), min(rows, scene.scene.Height)), state.Done
}
func (scene *Scene) FallbackFrame(cols, rows int) Cells {
	if scene == nil || scene.scene == nil {
		return nil
	}
	return cells.Render(eval.At(scene.scene, scene.Fallback), min(cols, scene.scene.Width), min(rows, scene.scene.Height))
}
func (scene *Scene) Active(time float64) bool {
	return scene != nil && scene.scene != nil && model.Finite(time) && eval.Active(scene.scene, time)
}
