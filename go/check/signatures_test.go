package check_test

import (
	"strings"
	"testing"

	"github.com/enmaq/mdgl/go/check"
	"github.com/enmaq/mdgl/go/parse"
)

func TestSignaturesCheck(t *testing.T) {
	for _, signature := range check.Signatures() {
		t.Run(signature, func(t *testing.T) {
			source := "scene width=32 height=10 fallback=end\n"
			if strings.HasPrefix(signature, "@") {
				source += "actor label = text(\"Hi\") at (0,0)\nactor box = cube(size=6,style=wire) at (0,0)\n"
			}
			scene, err := parse.Parse(source + signature)
			if err == nil {
				err = check.Check(scene)
			}
			if err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestArgumentErrorsListValidNames(t *testing.T) {
	for _, test := range []struct {
		line string
		want string
	}{
		{`actor item = circle(r=2) at (0,0)`, "valid arguments: positional 1"},
		{`actor item = circle(radius=2) at (0,0)`, "valid arguments: positional 1"},
		{`actor item = rect(width=2,height=1) at (0,0)`, "valid arguments: positional 1, positional 2, border, title"},
		{`actor item = rect(w=2,h=1) at (0,0)`, "valid arguments: positional 1, positional 2, border, title"},
		{`@0: label.type(dur=2)`, "valid arguments: per_char"},
		{`@0: label.fade(to=0)`, "valid arguments: positional 1, dur, ease"},
	} {
		t.Run(test.line, func(t *testing.T) {
			source := "scene width=32 height=10 fallback=end\nactor label = text(\"Hi\") at (0,0)\n" + test.line
			scene, err := parse.Parse(source)
			if err == nil {
				err = check.Check(scene)
			}
			if err == nil || !strings.Contains(err.Error(), "3:1:") || !strings.Contains(err.Error(), test.want) ||
				strings.Contains(err.Error(), `did you mean "0"`) || strings.Contains(err.Error(), `did you mean "1"`) {
				t.Fatalf("error=%v want=%q without numeric suggestion", err, test.want)
			}
		})
	}
}
