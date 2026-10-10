package eval

import (
	"math"
	"sort"

	"github.com/enmaq/mdgl/go/check"
	"github.com/enmaq/mdgl/go/internal/geometry"
	"github.com/enmaq/mdgl/go/model"
)

func Active(scene *model.Scene, time float64) bool {
	return scene.Period > 0 && (scene.Repeat == 0 || model.Time(time) < model.Time(scene.Period*float64(scene.Repeat)))
}
func Frame(scene *model.Scene, time float64) model.State {
	if !model.Finite(time) || time < 0 {
		time = 0
	}
	time = model.Time(time)
	done := !Active(scene, time)
	if scene.Period > 0 {
		if done {
			time = scene.Period
		} else {
			time = model.Time(math.Mod(time, scene.Period))
			if time == scene.Period {
				time = 0
			}
		}
	}
	state := At(scene, time)
	state.Done = done
	return state
}
func At(scene *model.Scene, time float64) model.State {
	time = math.Max(0, math.Min(scene.Period, time))
	state := model.State{Width: scene.Width, Height: scene.Height}
	names := map[string]int{}
	for index, actor := range scene.Actors {
		names[actor.Name] = index
	}
	for _, actor := range scene.Actors {
		width, height := float64(scene.Width), float64(scene.Height)
		if actor.Parent != "" {
			parent := scene.Actors[names[actor.Parent]]
			width, height = parent.Width, parent.Height
		}
		state.Actors = append(state.Actors, model.ActorState{Actor: actor, X: check.Resolve(actor.X, width, actor.Width), Y: check.Resolve(actor.Y, height, actor.Height), Z: actor.Z, Scale: 1, Opacity: 1, Reveal: 1, Color: actor.Color})
	}
	actions := append([]model.Action(nil), scene.Actions...)
	sort.SliceStable(actions, func(first, second int) bool { return actions[first].Begin < actions[second].Begin })
	initialized := map[string]bool{}
	for _, action := range actions {
		target := &state.Actors[names[action.Actor]]
		key := action.Actor + "/" + action.Property
		if !initialized[key] {
			initialized[key] = true
			if action.Verb == "fade" && action.Args["0"].Text == "in" {
				target.Opacity = 0
			}
			if action.Verb == "type" || action.Verb == "wipe" && action.Args["0"].Text == "in" {
				target.Reveal = 0
			}
			if action.Verb == "slide" && action.Args["0"].Text == "in" && time < action.Begin {
				target.X, target.Y = outside(scene, *target, action.Args["to"].Text)
			}
		}
		if time < action.Begin {
			continue
		}
		progress := 1.0
		if action.Duration > 0 {
			progress = math.Min(1, (time-action.Begin)/action.Duration)
		}
		if time >= model.Time(action.Begin+action.Duration) {
			progress = 1
		}
		eased := Ease(action.Ease, progress)
		switch action.Verb {
		case "fade":
			if action.Args["0"].Text == "in" {
				target.Opacity = eased
			} else {
				target.Opacity = 1 - eased
			}
		case "move":
			width, height := float64(scene.Width), float64(scene.Height)
			if target.Actor.Parent != "" {
				parent := scene.Actors[names[target.Actor.Parent]]
				width, height = parent.Width, parent.Height
			}
			point := action.Args["to"].Pair
			target.X = mix(target.X, check.Resolve(point[0], width, target.Actor.Width), eased)
			target.Y = mix(target.Y, check.Resolve(point[1], height, target.Actor.Height), eased)
		case "slide":
			edgeX, edgeY := outside(scene, *target, action.Args["to"].Text)
			if action.Args["0"].Text == "in" {
				target.X = mix(edgeX, target.X, eased)
				target.Y = mix(edgeY, target.Y, eased)
			} else {
				target.X = mix(target.X, edgeX, eased)
				target.Y = mix(target.Y, edgeY, eased)
			}
		case "scale":
			target.Scale = mix(target.Scale, check.Number(action.Args["to"]), eased)
		case "color":
			if eased >= 0.5 {
				target.Color = action.Args["to"].Text
			}
		case "type":
			count := float64(len(model.Glyphs(target.Actor.Text)))
			if count == 0 {
				target.Reveal = 1
			} else {
				target.Reveal = math.Min(count, math.Floor((time-action.Begin)/check.Number(action.Args["per_char"])+1e-9)) / count
			}
		case "wipe":
			target.Reveal = eased
			if action.Args["0"].Text == "out" {
				target.Reveal = 1 - eased
			}
		case "blink":
			target.Opacity = 1
			if progress < 1 && int(math.Floor(progress*check.Number(action.Args["times"])*2))%2 == 1 {
				target.Opacity = 0
			}
		case "rotate":
			for axis, name := range []string{"x", "y", "z"} {
				if value, exists := action.Args[name]; exists {
					target.Rotation[axis] = mix(target.Rotation[axis], check.Number(value), eased)
				}
			}
		}
	}
	composed := make([]bool, len(state.Actors))
	var compose func(int)
	compose = func(index int) {
		if composed[index] {
			return
		}
		actor := &state.Actors[index]
		anchorX, anchorY := actor.Actor.Width/2, actor.Actor.Height/2
		if anchor, exists := actor.Actor.Attr["anchor"]; exists {
			anchorX = check.Resolve(anchor.Pair[0], actor.Actor.Width, 0)
			anchorY = check.Resolve(anchor.Pair[1], actor.Actor.Height, 0)
		}
		actor.Transform = geometry.Mul(geometry.Compose([3]float64{actor.X + anchorX, -2 * (actor.Y + anchorY), 0}, actor.Rotation, [3]float64{actor.Scale, actor.Scale, actor.Scale}), geometry.Translation(-anchorX, 2*anchorY, 0))
		if actor.Actor.Parent != "" {
			parentIndex := names[actor.Actor.Parent]
			compose(parentIndex)
			parent := state.Actors[parentIndex]
			actor.Transform = geometry.Mul(parent.Transform, actor.Transform)
			actor.Scale *= parent.Scale
			actor.Opacity *= parent.Opacity
			actor.Reveal *= parent.Reveal
		}
		origin := geometry.Transform(actor.Transform, geometry.Vec4{0, 0, 0, 1})
		actor.X, actor.Y = origin[0], -origin[1]/2
		composed[index] = true
	}
	for index := range state.Actors {
		compose(index)
	}
	return state
}
func outside(scene *model.Scene, actor model.ActorState, direction string) (float64, float64) {
	horizontal, vertical := actor.X, actor.Y
	width, height := float64(scene.Width), float64(scene.Height)
	if actor.Actor.Parent != "" {
		for _, parent := range scene.Actors {
			if parent.Name == actor.Actor.Parent {
				width, height = parent.Width, parent.Height
				break
			}
		}
	}
	switch direction {
	case "left":
		horizontal = -actor.Actor.Width * actor.Scale
	case "right":
		horizontal = width
	case "top":
		vertical = -actor.Actor.Height * actor.Scale
	case "bottom":
		vertical = height
	}
	return horizontal, vertical
}
func mix(start, end, progress float64) float64 { return start + (end-start)*progress }
func Ease(name string, progress float64) float64 {
	progress = math.Max(0, math.Min(1, progress))
	switch name {
	case "ease":
		return cubicBezier(progress, 0.25, 0.1, 0.25, 1)
	case "ease-in":
		return cubicBezier(progress, 0.42, 0, 1, 1)
	case "ease-out":
		return cubicBezier(progress, 0, 0, 0.58, 1)
	case "ease-in-out":
		return cubicBezier(progress, 0.42, 0, 0.58, 1)
	case "bounce":
		divisor := 2.75
		if progress < 1/divisor {
			return 7.5625 * progress * progress
		}
		if progress < 2/divisor {
			progress -= 1.5 / divisor
			return 7.5625*progress*progress + 0.75
		}
		if progress < 2.5/divisor {
			progress -= 2.25 / divisor
			return 7.5625*progress*progress + 0.9375
		}
		progress -= 2.625 / divisor
		return 7.5625*progress*progress + 0.984375
	}
	return progress
}

func cubicBezier(progress, firstX, firstY, secondX, secondY float64) float64 {
	if progress == 0 || progress == 1 {
		return progress
	}
	sample := func(parameter, first, second float64) float64 {
		inverse := 1 - parameter
		return 3*inverse*inverse*parameter*first + 3*inverse*parameter*parameter*second + parameter*parameter*parameter
	}
	lower, upper := 0.0, 1.0
	for iteration := 0; iteration < 60; iteration++ {
		middle := (lower + upper) / 2
		if sample(middle, firstX, secondX) < progress {
			lower = middle
		} else {
			upper = middle
		}
	}
	return sample((lower+upper)/2, firstY, secondY)
}
