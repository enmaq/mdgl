package parse

import (
	"fmt"
	"strconv"
	"strings"
	"unicode/utf8"

	"github.com/enmaq/mdgl/go/model"
)

type token struct {
	text   string
	col    int
	quoted bool
}
type parser struct {
	tokens []token
	offset int
	pos    model.Pos
}

func Parse(source string) (*model.Scene, error) {
	if len(source) > 256*1024 {
		return nil, model.Pos{Line: 1, Col: 1}.Error("input exceeds 256 KiB")
	}
	if !utf8.ValidString(source) {
		return nil, model.Pos{Line: 1, Col: 1}.Error("input is not UTF-8")
	}
	scene := &model.Scene{}
	seenScene, seenAction, seenVersion := false, false, false
	for index, line := range strings.Split(source, "\n") {
		pos := model.Pos{Line: index + 1, Col: 1}
		if len(line) > 16384 {
			return nil, pos.Error("line exceeds 16 KiB")
		}
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			continue
		}
		tokens, err := lex(line, pos)
		if err != nil {
			return nil, err
		}
		reader := parser{tokens: tokens, pos: pos}
		head := reader.take()
		if head.quoted {
			return nil, pos.Error("expected statement identifier")
		}
		pos.Col = head.col
		reader.pos = pos
		switch head.text {
		case "mdgl":
			version := reader.take()
			if seenScene || seenVersion || version.quoted || version.text != "0.1" || !reader.end() {
				return nil, pos.Error("expected initial mdgl 0.1")
			}
			seenVersion = true
		case "scene":
			if seenScene {
				return nil, pos.Error("duplicate scene")
			}
			scene.Pos = pos
			scene.Attr, err = reader.attributes()
			seenScene = true
		case "actor":
			if !seenScene {
				return nil, pos.Error("scene must precede actors")
			}
			if seenAction {
				return nil, pos.Error("actors must precede actions")
			}
			name := reader.take()
			actor := model.Actor{Pos: pos, Name: name.text}
			if name.quoted || !identifier(actor.Name) {
				return nil, pos.Error("expected actor identifier")
			}
			if err = reader.want("="); err != nil {
				return nil, err
			}
			kind := reader.take()
			if kind.quoted || !identifier(kind.text) {
				return nil, pos.Error("expected shape identifier")
			}
			actor.Kind = kind.text
			actor.Args, err = reader.arguments()
			if err != nil {
				return nil, err
			}
			if err = reader.want("at"); err != nil {
				return nil, err
			}
			point, pointErr := reader.value()
			if pointErr != nil {
				return nil, pointErr
			}
			if len(point.Pair) != 2 {
				return nil, pos.Error("expected (x, y) position")
			}
			actor.X, actor.Y = point.Pair[0], point.Pair[1]
			actor.Attr, err = reader.attributes()
			scene.Actors = append(scene.Actors, actor)
			if len(scene.Actors) > 64 {
				return nil, pos.Error("actor limit 64 exceeded")
			}
		case "@":
			if !seenScene {
				return nil, pos.Error("scene must precede actions")
			}
			seenAction = true
			value, valueErr := reader.value()
			if valueErr != nil {
				return nil, valueErr
			}
			begin, numberErr := strconv.ParseFloat(strings.TrimSuffix(value.Text, "s"), 64)
			if value.Quoted || len(value.Pair) > 0 || numberErr != nil || !model.Finite(begin) || begin < 0 {
				return nil, pos.Error("invalid action time")
			}
			if err = reader.want(":"); err != nil {
				return nil, err
			}
			name := reader.take()
			action := model.Action{Pos: pos, Begin: begin, Actor: name.text}
			if name.quoted || !identifier(action.Actor) {
				return nil, pos.Error("expected actor identifier")
			}
			if err = reader.want("."); err != nil {
				return nil, err
			}
			verb := reader.take()
			if verb.quoted || !identifier(verb.text) {
				return nil, pos.Error("expected action identifier")
			}
			action.Verb = verb.text
			action.Args, err = reader.arguments()
			if err == nil && !reader.end() {
				err = reader.failure("unexpected token " + strconv.Quote(reader.peek().text))
			}
			scene.Actions = append(scene.Actions, action)
			if len(scene.Actions) > 1024 {
				return nil, pos.Error("action limit 1024 exceeded")
			}
		case "camera", "light", "mesh", "material", "threejs":
			return nil, pos.Error(head.text + " is reserved; not yet supported in 0.1")
		default:
			message := Unknown("statement", head.text, []string{"mdgl", "scene", "actor", "@"})
			message += "; expected scene ..., actor NAME = KIND(...) at (X,Y), or @T: NAME.ACTION(...)"
			switch head.text {
			case "text", "rect", "circle", "cube":
				message += "; use actor NAME = " + head.text + "(...) at (X,Y)"
			}
			return nil, pos.Error(message)
		}
		if err != nil {
			return nil, err
		}
	}
	if !seenScene {
		return nil, model.Pos{Line: 1, Col: 1}.Error("missing scene")
	}
	return scene, nil
}

func lex(line string, pos model.Pos) ([]token, error) {
	result := []token{}
	for offset := 0; offset < len(line); {
		current := line[offset]
		if current == ' ' || current == '\t' || current == '\r' {
			offset++
			continue
		}
		start := offset
		if current == '"' {
			offset++
			closed := false
			for offset < len(line) {
				if line[offset] == '\\' {
					offset += 2
					continue
				}
				if line[offset] == '"' {
					offset++
					closed = true
					break
				}
				offset++
			}
			if !closed {
				return nil, model.Pos{Line: pos.Line, Col: start + 1}.Error("unterminated string")
			}
			value, err := strconv.Unquote(line[start:offset])
			if err != nil {
				return nil, model.Pos{Line: pos.Line, Col: start + 1}.Error("invalid string escape")
			}
			result = append(result, token{text: value, col: start + 1, quoted: true})
			continue
		}
		if digit(current) || current == '.' && offset+1 < len(line) && digit(line[offset+1]) {
			offset++
			for offset < len(line) && (digit(line[offset]) || line[offset] == '.') {
				offset++
			}
			if strings.HasPrefix(line[offset:], "rad") || strings.HasPrefix(line[offset:], "deg") {
				offset += 3
			} else if offset < len(line) && (line[offset] == 's' || line[offset] == '%') {
				offset++
			}
		} else if letter(current) {
			offset++
			for offset < len(line) && (letter(line[offset]) || digit(line[offset]) || line[offset] == '-') {
				offset++
			}
		} else if strings.ContainsRune("=(),@:.+-", rune(current)) {
			offset++
		} else {
			return nil, model.Pos{Line: pos.Line, Col: start + 1}.Error("unexpected character " + strconv.Quote(string(current)))
		}
		result = append(result, token{text: line[start:offset], col: start + 1})
	}
	return result, nil
}
func digit(character byte) bool { return character >= '0' && character <= '9' }
func letter(character byte) bool {
	return character >= 'a' && character <= 'z' || character >= 'A' && character <= 'Z' || character == '_'
}
func identifier(value string) bool {
	if len(value) == 0 || !letter(value[0]) {
		return false
	}
	for _, character := range []byte(value) {
		if !letter(character) && !digit(character) {
			return false
		}
	}
	return true
}
func (reader *parser) end() bool { return reader.offset >= len(reader.tokens) }
func (reader *parser) peek() token {
	if reader.end() {
		return token{text: "<end>", col: reader.pos.Col}
	}
	return reader.tokens[reader.offset]
}
func (reader *parser) take() token {
	current := reader.peek()
	if !reader.end() {
		reader.offset++
	}
	return current
}
func (reader *parser) failure(message string) error {
	return model.Pos{Line: reader.pos.Line, Col: reader.peek().col}.Error(message)
}
func (reader *parser) want(text string) error {
	if reader.peek().text != text || reader.peek().quoted {
		return reader.failure("expected " + strconv.Quote(text))
	}
	reader.take()
	return nil
}

func (reader *parser) is(text string) bool {
	return !reader.peek().quoted && reader.peek().text == text
}
func (reader *parser) value() (model.Value, error) {
	current := reader.take()
	if current.quoted {
		return model.Value{Text: current.text, Quoted: true}, nil
	}
	if current.text == "<end>" {
		return model.Value{}, reader.failure("expected value")
	}
	if current.text == "(" {
		first, err := reader.value()
		if err != nil {
			return model.Value{}, err
		}
		if err = reader.want(","); err != nil {
			return model.Value{}, err
		}
		second, err := reader.value()
		if err != nil {
			return model.Value{}, err
		}
		pair := []model.Value{first, second}
		if reader.peek().text == "," {
			reader.take()
			third, thirdErr := reader.value()
			if thirdErr != nil {
				return model.Value{}, thirdErr
			}
			pair = append(pair, third)
		}
		if err = reader.want(")"); err != nil {
			return model.Value{}, err
		}
		return model.Value{Pair: pair}, nil
	}
	if current.text == "+" || current.text == "-" || current.text == "@" {
		next := reader.take()
		if next.text == "<end>" {
			return model.Value{}, reader.failure("expected value")
		}
		current.text += next.text
	}
	if reader.peek().text == "+" || reader.peek().text == "-" {
		current.text += reader.take().text + reader.take().text
	}
	if strings.ContainsAny(current.text, "=),:") {
		return model.Value{}, reader.failure("expected value")
	}
	return model.Value{Text: current.text}, nil
}
func (reader *parser) attributes() (model.Args, error) {
	result := model.Args{}
	for !reader.end() {
		name := reader.take()
		if name.quoted || !identifier(name.text) {
			return nil, reader.pos.Error("expected attribute identifier")
		}
		key := name.text
		if err := reader.want("="); err != nil {
			return nil, err
		}
		value, err := reader.value()
		if err != nil {
			return nil, err
		}
		if _, exists := result[key]; exists {
			return nil, reader.pos.Error("duplicate attribute " + key)
		}
		result[key] = value
	}
	return result, nil
}
func (reader *parser) arguments() (model.Args, error) {
	if err := reader.want("("); err != nil {
		return nil, err
	}
	result := model.Args{}
	ordinal := 0
	for !reader.is(")") {
		if reader.end() {
			return nil, reader.failure("expected \")\"")
		}
		key := fmt.Sprint(ordinal)
		ordinal++
		if reader.offset+1 < len(reader.tokens) && reader.tokens[reader.offset+1].text == "=" {
			name := reader.take()
			if name.quoted || !identifier(name.text) {
				return nil, reader.pos.Error("expected argument identifier")
			}
			key = name.text
			reader.take()
		}
		value, err := reader.value()
		if err != nil {
			return nil, err
		}
		if _, exists := result[key]; exists {
			return nil, reader.pos.Error("duplicate argument " + key)
		}
		result[key] = value
		if reader.is(")") {
			break
		}
		if err = reader.want(","); err != nil {
			return nil, err
		}
		if reader.is(")") {
			return nil, reader.failure("trailing comma")
		}
	}
	reader.take()
	return result, nil
}

func Unknown(kind, name string, choices []string) string {
	best := ""
	distance := 3
	for _, choice := range choices {
		current := editDistance(name, choice)
		if current < distance || current == distance && choice < best {
			best = choice
			distance = current
		}
	}
	message := fmt.Sprintf("unknown %s %q", kind, name)
	if distance <= 2 {
		message += fmt.Sprintf("; did you mean %q?", best)
	}
	return message
}
func editDistance(first, second string) int {
	row := make([]int, len(second)+1)
	for index := range row {
		row[index] = index
	}
	for firstIndex := range first {
		diagonal := row[0]
		row[0] = firstIndex + 1
		for secondIndex := range second {
			saved := row[secondIndex+1]
			cost := 0
			if first[firstIndex] != second[secondIndex] {
				cost = 1
			}
			row[secondIndex+1] = min(row[secondIndex]+1, row[secondIndex+1]+1, diagonal+cost)
			diagonal = saved
		}
	}
	return row[len(second)]
}
