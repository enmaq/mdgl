package eval

import (
	"math"
	"testing"
)

func TestCSSBezierReferences(t *testing.T) {
	references := map[string][5]float64{
		"ease":        {0, .4085105913553959, .802403387584857, .9604589783489741, 1},
		"ease-in":     {0, .0934646507188248, .3153568125725393, .6218618691748903, 1},
		"ease-out":    {0, .3781381308251097, .6846431874274608, .9065353492811752, 1},
		"ease-in-out": {0, .1291619310473198, .5, .8708380689526802, 1},
	}
	for name, values := range references {
		for index, want := range values {
			if got := Ease(name, float64(index)/4); math.Abs(got-want) > 1e-9 {
				t.Fatalf("%s(%g)=%g want%g", name, float64(index)/4, got, want)
			}
		}
	}
}
