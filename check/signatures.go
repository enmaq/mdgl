package check

type syntax struct {
	arguments []string
	line      string
}

var shapeSyntax = map[string]syntax{
	"text":   {[]string{"0", "1"}, `actor label = text("Hi",big) at (0,0)`},
	"rect":   {[]string{"0", "1", "border", "title"}, `actor frame = rect(8,4,border=round,title="Box") at (0,0)`},
	"circle": {[]string{"0"}, `actor orb = circle(2) at (0,0)`},
	"cube":   {[]string{"size", "style"}, `actor box = cube(size=6,style=wire) at (0,0)`},
}

var actionSyntax = map[string]syntax{
	"fade":   {[]string{"0", "dur", "ease"}, `@0: label.fade(in,dur=1,ease=linear)`},
	"move":   {[]string{"to", "dur", "ease"}, `@0: label.move(to=(4,2),dur=1,ease=ease-in-out)`},
	"scale":  {[]string{"to", "dur", "ease"}, `@0: label.scale(to=2,dur=1,ease=linear)`},
	"color":  {[]string{"to", "dur", "ease"}, `@0: label.color(to=red,dur=1,ease=linear)`},
	"type":   {[]string{"per_char"}, `@0: label.type(per_char=0.1)`},
	"rotate": {[]string{"x", "y", "z", "dur", "ease"}, `@0: box.rotate(x=30,y=45,z=90,dur=1,ease=linear)`},
	"blink":  {[]string{"times", "dur"}, `@0: label.blink(times=3,dur=1)`},
	"wipe":   {[]string{"0", "dur", "ease"}, `@0: label.wipe(out,dur=1,ease=linear)`},
	"slide":  {[]string{"0", "to", "dur", "ease"}, `@0: label.slide(in,to=left,dur=1,ease=linear)`},
}

func Signatures() []string {
	lines := make([]string, 0, len(shapeSyntax)+len(actionSyntax))
	for _, kind := range []string{"text", "rect", "circle", "cube"} {
		lines = append(lines, shapeSyntax[kind].line)
	}
	for _, verb := range []string{"fade", "move", "scale", "color", "type", "rotate", "blink", "wipe", "slide"} {
		lines = append(lines, actionSyntax[verb].line)
	}
	return lines
}
