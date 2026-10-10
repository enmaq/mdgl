package parse

import (
	"strings"
	"testing"
)

func TestUnknownStatementGuidance(t *testing.T) {
	for _, kind := range []string{"text", "rect", "circle", "cube"} {
		t.Run(kind, func(t *testing.T) {
			_, err := Parse(kind + " title x")
			want := "1:1: " + Unknown("statement", kind, []string{"mdgl", "scene", "actor", "@"}) +
				"; expected scene ..., actor NAME = KIND(...) at (X,Y), or @T: NAME.ACTION(...)" +
				"; use actor NAME = " + kind + "(...) at (X,Y)"
			if err == nil || err.Error() != want {
				t.Fatalf("error=%v want=%q", err, want)
			}
		})
	}
	_, err := Parse("\n  scen width=10 height=2")
	if err == nil || !strings.HasPrefix(err.Error(), "2:3: unknown statement \"scen\"; did you mean \"scene\"?") ||
		!strings.Contains(err.Error(), "@T: NAME.ACTION(...)") || strings.Contains(err.Error(), "; use actor") {
		t.Fatalf("missing position, suggestion, or expected forms: %v", err)
	}
}
