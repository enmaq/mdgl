package check

import (
	"fmt"
	"math"
	"sort"
	"strconv"
	"strings"
	"unicode"

	"github.com/enmaq/mdgl/model"
	"github.com/enmaq/mdgl/parse"
)

var Colors = []string{"normal", "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white", "accent"}
var Eases = []string{"linear", "ease", "ease-in", "ease-out", "ease-in-out", "bounce"}
var Verbs = []string{"fade", "move", "scale", "color", "type", "blink", "wipe", "slide", "rotate"}

func Check(scene *model.Scene) error {
	if scene == nil {
		return fmt.Errorf("1:1: missing scene")
	}
	fail := scene.Pos.Error
	if err := keys(scene.Attr, []string{"width", "height", "period", "repeat", "fallback", "fps"}, "scene attribute"); err != nil {
		return fail(err.Error())
	}
	for _, required := range []string{"width", "height", "fallback"} {
		if _, exists := scene.Attr[required]; !exists {
			return fail("missing scene attribute " + required)
		}
	}
	width, err := integer(scene.Attr["width"], 1, 200, "width")
	if err != nil {
		return fail(err.Error())
	}
	scene.Width = width
	height, err := integer(scene.Attr["height"], 1, 60, "height")
	if err != nil {
		return fail(err.Error())
	}
	scene.Height = height
	scene.FPS = 30
	if value, exists := scene.Attr["fps"]; exists {
		scene.FPS, err = integer(value, 1, 30, "fps")
		if err != nil {
			return fail(err.Error())
		}
	}
	scene.Period = 0
	scene.ExplicitPeriod = false
	scene.Repeat = 1
	if value, exists := scene.Attr["period"]; exists {
		scene.ExplicitPeriod = true
		scene.Period, err = number(value)
		if err != nil || scene.Period <= 0 || scene.Period > 60 {
			return fail("period must be positive and <=60")
		}
		scene.Period = model.Time(scene.Period)
		if scene.Period == 0 {
			return fail("period rounds to zero at nanosecond precision")
		}
	}
	if value, exists := scene.Attr["repeat"]; exists {
		if value.Text == "infinite" && !value.Quoted {
			scene.Repeat = 0
		} else {
			scene.Repeat, err = integer(value, 1, 1000, "repeat")
			if err != nil {
				return fail(err.Error())
			}
		}
		if scene.Repeat != 1 && !scene.ExplicitPeriod {
			return fail("repeat requires explicit period")
		}
	}
	scene.Fallback = scene.Attr["fallback"].Text
	if scene.Attr["fallback"].Quoted || len(scene.Attr["fallback"].Pair) > 0 {
		return fail("fallback must be start, end or @time")
	}
	names := map[string]int{}
	orderedNames := []string{}
	for index := range scene.Actors {
		actor := &scene.Actors[index]
		failActor := actor.Pos.Error
		if _, exists := names[actor.Name]; exists {
			return failActor("duplicate actor " + actor.Name)
		}
		names[actor.Name] = index
		orderedNames = append(orderedNames, actor.Name)
		if err = keys(actor.Attr, []string{"color", "parent", "z", "anchor"}, "actor attribute"); err != nil {
			return failActor(err.Error())
		}
		actor.Color = "normal"
		actor.Parent = ""
		actor.Scale = 1
		if value, exists := actor.Attr["color"]; exists {
			if !oneOf(value, Colors) {
				return failActor(parse.Unknown("color", value.Text, Colors))
			}
			actor.Color = value.Text
		}
		if value, exists := actor.Attr["parent"]; exists {
			if value.Quoted || len(value.Pair) > 0 {
				return failActor("parent must be an actor identifier")
			}
			actor.Parent = value.Text
		}
		if value, exists := actor.Attr["z"]; exists {
			depth, depthErr := integer(value, -10000, 10000, "z")
			if depthErr != nil {
				return failActor(depthErr.Error())
			}
			actor.Z = float64(depth)
		}
		switch actor.Kind {
		case "text":
			if err = keys(actor.Args, shapeSyntax[actor.Kind].arguments, "text argument"); err != nil {
				return failActor(err.Error())
			}
			text, exists := actor.Args["0"]
			if !exists || !text.Quoted {
				return failActor("text requires a quoted string")
			}
			actor.Text = text.Text
			if value, exists := actor.Args["1"]; exists && (value.Text != "big" || value.Quoted) {
				return failActor("text style must be big")
			}
			if err = validateText(actor.Text); err != nil {
				return failActor(err.Error())
			}
			actor.Width = float64(len(model.Glyphs(actor.Text)))
			actor.Height = 1
		case "rect":
			if err = keys(actor.Args, shapeSyntax[actor.Kind].arguments, "rect argument"); err != nil {
				return failActor(err.Error())
			}
			actor.Width, err = dimension(actor.Args["0"])
			if err != nil {
				return failActor("rect width must be positive and <=200")
			}
			actor.Height, err = dimension(actor.Args["1"])
			if err != nil {
				return failActor("rect height must be positive and <=200")
			}
			if value, exists := actor.Args["border"]; exists && !oneOf(value, []string{"round", "square"}) {
				return failActor("border must be round or square")
			}
			if value, exists := actor.Args["title"]; exists {
				if !value.Quoted {
					return failActor("title requires a quoted string")
				}
				actor.Text = value.Text
				if err = validateText(actor.Text); err != nil {
					return failActor(err.Error())
				}
			}
		case "circle":
			if err = keys(actor.Args, shapeSyntax[actor.Kind].arguments, "circle argument"); err != nil {
				return failActor(err.Error())
			}
			radius, radiusErr := dimension(actor.Args["0"])
			if radiusErr != nil || radius > 100 {
				return failActor("circle radius must be positive and <=100")
			}
			actor.Width = radius * 2
			actor.Height = radius * 2
		case "cube":
			if err = keys(actor.Args, shapeSyntax[actor.Kind].arguments, "cube argument"); err != nil {
				return failActor(err.Error())
			}
			actor.Width, err = dimension(actor.Args["size"])
			if err != nil {
				return failActor("cube size must be positive and <=200")
			}
			actor.Height = actor.Width
			if value, exists := actor.Args["style"]; exists && !oneOf(value, []string{"wire"}) {
				return failActor("only cube style=wire is supported in 0.1")
			}
		case "mesh", "sphere", "plane", "threejs", "cells":
			return failActor(actor.Kind + " is reserved; not yet supported in 0.1")
		default:
			return failActor(parse.Unknown("shape", actor.Kind, []string{"text", "rect", "circle", "cube"}))
		}
		if err = coordinate(actor.X, true); err != nil {
			return failActor(err.Error())
		}
		if err = coordinate(actor.Y, false); err != nil {
			return failActor(err.Error())
		}
		if value, exists := actor.Attr["anchor"]; exists {
			if len(value.Pair) != 2 {
				return failActor("anchor requires (x, y)")
			}
			for axis, coordinateValue := range value.Pair {
				if err = coordinate(coordinateValue, axis == 0); err != nil {
					return failActor(err.Error())
				}
			}
		}
	}
	for _, actor := range scene.Actors {
		if actor.Parent != "" {
			if _, exists := names[actor.Parent]; !exists {
				return actor.Pos.Error(parse.Unknown("parent", actor.Parent, orderedNames))
			}
		}
	}
	for _, actor := range scene.Actors {
		seen := map[string]bool{}
		current := actor
		for current.Parent != "" {
			if seen[current.Name] {
				return actor.Pos.Error("parent cycle involving " + actor.Name)
			}
			seen[current.Name] = true
			current = scene.Actors[names[current.Parent]]
		}
	}
	for index := range scene.Actions {
		action := &scene.Actions[index]
		failAction := action.Pos.Error
		actorIndex, exists := names[action.Actor]
		if !exists {
			return failAction(parse.Unknown("actor", action.Actor, orderedNames))
		}
		actor := scene.Actors[actorIndex]
		if !contains(Verbs, action.Verb) {
			return failAction(parse.Unknown("action", action.Verb, Verbs))
		}
		if !model.Finite(action.Begin) || action.Begin < 0 {
			return failAction("invalid action time")
		}
		action.Begin = model.Time(action.Begin)
		allowed := actionSyntax[action.Verb].arguments
		if err = keys(action.Args, allowed, "action argument"); err != nil {
			return failAction(err.Error())
		}
		action.Ease = "linear"
		switch action.Verb {
		case "fade", "wipe":
			if !oneOf(action.Args["0"], []string{"in", "out"}) {
				return failAction(action.Verb + " requires in or out")
			}
		case "move", "scale", "color":
		case "slide":
			if !oneOf(action.Args["0"], []string{"in", "out"}) {
				return failAction("slide requires in or out")
			}
			if !oneOf(action.Args["to"], []string{"left", "right", "top", "bottom"}) {
				return failAction("slide to must be left, right, top or bottom")
			}
		case "type":
			if actor.Kind != "text" {
				return failAction("type requires a text actor")
			}
		case "blink":
			if _, err = integer(action.Args["times"], 1, 1000, "times"); err != nil {
				return failAction(err.Error())
			}
		case "rotate":
			if actor.Kind != "cube" {
				return failAction("rotate requires a cube actor")
			}
			found := false
			for _, axis := range []string{"x", "y", "z"} {
				if value, exists := action.Args[axis]; exists {
					found = true
					angle, angleErr := angleDegrees(value)
					if angleErr != nil || math.Abs(angle) > 10000 {
						return failAction("rotation must be within -10000..10000")
					}
					action.Args[axis] = model.Value{Text: strconv.FormatFloat(angle, 'f', -1, 64)}
				}
			}
			if !found {
				return failAction("rotate requires x, y or z")
			}
		}
		if value, exists := action.Args["ease"]; exists {
			if !oneOf(value, Eases) {
				return failAction(parse.Unknown("easing", value.Text, Eases))
			}
			action.Ease = value.Text
		}
		if action.Verb == "type" {
			seconds, secondsErr := number(action.Args["per_char"])
			if secondsErr != nil || seconds <= 0 {
				return failAction("per_char must be positive")
			}
			seconds = model.Time(seconds)
			if seconds == 0 {
				return failAction("per_char rounds to zero at nanosecond precision")
			}
			action.Args["per_char"] = model.Value{Text: strconv.FormatFloat(seconds, 'f', -1, 64)}
			action.Duration = seconds * float64(len(model.Glyphs(actor.Text)))
		} else {
			action.Duration, err = number(action.Args["dur"])
			if err != nil || action.Duration <= 0 {
				return failAction("dur must be positive")
			}
		}
		switch action.Verb {
		case "fade", "blink":
			action.Property = "opacity"
		case "type", "wipe":
			action.Property = "reveal"
		case "move", "slide":
			action.Property = "position"
		case "scale":
			action.Property = "scale"
		case "color":
			action.Property = "color"
		case "rotate":
			action.Property = "rotation"
		}
		switch action.Verb {
		case "move":
			point := action.Args["to"].Pair
			if len(point) != 2 {
				return failAction("move requires to=(x, y)")
			}
			if err = coordinate(point[0], true); err != nil {
				return failAction(err.Error())
			}
			if err = coordinate(point[1], false); err != nil {
				return failAction(err.Error())
			}
		case "scale":
			factor, factorErr := number(action.Args["to"])
			if factorErr != nil || factor <= 0 || factor > 16 {
				return failAction("scale to must be positive and <=16")
			}
		case "color":
			if !oneOf(action.Args["to"], Colors) {
				return failAction(parse.Unknown("color", action.Args["to"].Text, Colors))
			}
		}
		action.Duration = model.Time(action.Duration)
		if action.Duration == 0 && action.Verb != "type" {
			return failAction("dur rounds to zero at nanosecond precision")
		}
		end := model.Time(action.Begin + action.Duration)
		if !model.Finite(end) || end > 60 {
			return failAction("action end must be <=60")
		}
		if scene.ExplicitPeriod {
			if end > scene.Period {
				return failAction("action exceeds period")
			}
		} else if end > scene.Period {
			scene.Period = end
		}
		for earlier := 0; earlier < index; earlier++ {
			other := scene.Actions[earlier]
			if action.Actor == other.Actor && action.Property == other.Property && action.Begin < model.Time(other.Begin+other.Duration) && other.Begin < end {
				return failAction("overlapping " + action.Property + " actions on " + action.Actor)
			}
		}
	}
	if scene.Fallback != "start" && scene.Fallback != "end" {
		if !strings.HasPrefix(scene.Fallback, "@") {
			return fail("fallback must be start, end or @time")
		}
		time, timeErr := number(model.Value{Text: strings.TrimPrefix(scene.Fallback, "@")})
		if timeErr != nil || time < 0 || time > scene.Period {
			return fail("fallback time must be within period")
		}
	}
	return nil
}

func validateText(text string) error {
	if len(model.Glyphs(text)) > 1024 {
		return fmt.Errorf("text exceeds 1024 graphemes")
	}
	for _, character := range text {
		if unicode.IsControl(character) || character == '\u2028' || character == '\u2029' {
			return fmt.Errorf("text contains a control character")
		}
	}
	return nil
}
func keys(args model.Args, allowed []string, kind string) error {
	names := make([]string, 0, len(args))
	for key := range args {
		names = append(names, key)
	}
	sort.Strings(names)
	for _, key := range names {
		if contains([]string{"camera", "light", "material", "position", "rotation", "threejs"}, key) {
			return fmt.Errorf("%s is reserved; not yet supported in 0.1", key)
		}
		if !contains(allowed, key) {
			if strings.HasSuffix(kind, "argument") {
				choices := []string{}
				valid := []string{}
				for _, name := range allowed {
					if position, err := strconv.Atoi(name); err == nil {
						valid = append(valid, fmt.Sprintf("positional %d", position+1))
					} else {
						choices = append(choices, name)
						valid = append(valid, name)
					}
				}
				return fmt.Errorf("%s; valid arguments: %s", parse.Unknown(kind, key, choices), strings.Join(valid, ", "))
			}
			return fmt.Errorf("%s", parse.Unknown(kind, key, allowed))
		}
	}
	return nil
}
func contains(values []string, value string) bool {
	for _, candidate := range values {
		if candidate == value {
			return true
		}
	}
	return false
}
func oneOf(value model.Value, choices []string) bool {
	return !value.Quoted && len(value.Pair) == 0 && contains(choices, value.Text)
}
func number(value model.Value) (float64, error) {
	if value.Quoted || len(value.Pair) > 0 {
		return 0, fmt.Errorf("expected number")
	}
	result, err := strconv.ParseFloat(strings.TrimSuffix(value.Text, "s"), 64)
	if err != nil || !model.Finite(result) {
		return 0, fmt.Errorf("expected finite number")
	}
	return result, nil
}
func Number(value model.Value) float64 { result, _ := number(value); return result }

func angleDegrees(value model.Value) (float64, error) {
	if strings.HasSuffix(value.Text, "rad") {
		value.Text = strings.TrimSuffix(value.Text, "rad")
		angle, err := number(value)
		return angle * 180 / math.Pi, err
	}
	value.Text = strings.TrimSuffix(value.Text, "deg")
	return number(value)
}
func integer(value model.Value, lower, upper int, name string) (int, error) {
	result, err := number(value)
	if err != nil || result != math.Trunc(result) || result < float64(lower) || result > float64(upper) {
		return 0, fmt.Errorf("%s must be an integer in %d..%d", name, lower, upper)
	}
	return int(result), nil
}
func dimension(value model.Value) (float64, error) {
	result, err := number(value)
	if err != nil || result <= 0 || result > 200 {
		return 0, fmt.Errorf("invalid dimension")
	}
	return result, nil
}
func coordinate(value model.Value, horizontal bool) error {
	if value.Quoted || len(value.Pair) > 0 {
		return fmt.Errorf("invalid coordinate")
	}
	text := value.Text
	if _, err := number(model.Value{Text: strings.TrimSuffix(text, "%")}); err == nil {
		result := Number(model.Value{Text: strings.TrimSuffix(text, "%")})
		if math.Abs(result) > 10000 {
			return fmt.Errorf("coordinate exceeds -10000..10000")
		}
		return nil
	}
	anchors := []string{"center", "left", "right"}
	if !horizontal {
		anchors = []string{"center", "top", "bottom"}
	}
	for _, anchor := range anchors {
		if text == anchor {
			return nil
		}
		if strings.HasPrefix(text, anchor+"+") || strings.HasPrefix(text, anchor+"-") {
			offset, err := number(model.Value{Text: strings.TrimPrefix(text, anchor)})
			if err == nil && math.Abs(offset) <= 10000 {
				return nil
			}
		}
	}
	return fmt.Errorf("invalid coordinate %q", text)
}
func Resolve(value model.Value, extent, size float64) float64 {
	text := value.Text
	remaining := extent - size
	if strings.HasSuffix(text, "%") {
		return Number(model.Value{Text: strings.TrimSuffix(text, "%")}) * remaining / 100
	}
	for _, anchor := range []string{"center", "left", "right", "top", "bottom"} {
		if strings.HasPrefix(text, anchor) {
			base := 0.0
			if anchor == "center" {
				base = remaining / 2
			}
			if anchor == "right" || anchor == "bottom" {
				base = remaining
			}
			tail := strings.TrimPrefix(text, anchor)
			if tail != "" {
				base += Number(model.Value{Text: tail})
			}
			return base
		}
	}
	return Number(value)
}
