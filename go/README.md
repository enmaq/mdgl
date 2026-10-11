# MDGL for Go

`github.com/enmaq/mdgl/go` is the Go module of MDGL, a small animation language
written in Markdown that renders as terminal cells. It parses and checks a
scene, evaluates it at any time, and returns a grid of cells. The latest published tag is
`v0.2.0` (nested tag `go/v0.2.0`); the source tree is the 0.3.0 release candidate (not yet tagged).

## Install

Published (0.2.0):

```
go get github.com/enmaq/mdgl/go@v0.2.0
go install github.com/enmaq/mdgl/go/cmd/mdgl@v0.2.0
```

From source (0.3.0 release candidate; no `v0.3.0` tag exists yet): in a checkout, `cd v/mdgl/go && go install ./cmd/mdgl`.

## Use

```go
package main

import (
	"fmt"
	"os"

	mdgl "github.com/enmaq/mdgl/go"
)

func main() {
	source, _ := os.ReadFile("text.mdgl")
	scene, diags := mdgl.Parse(string(source))
	if len(diags) > 0 {
		fmt.Fprintln(os.Stderr, diags[0]) // line:col: message
		os.Exit(1)
	}
	for _, line := range scene.Frame(1.5, scene.Width, scene.Height).Lines() {
		fmt.Println(line)
	}
	fmt.Println(scene.Active(1.5)) // false once the scene is done
}
```

`Frame` is a pure function of scene, time and size. `FallbackFrame(cols, rows)`
returns the still frame for readers that cannot animate.

## Example program

`examples/render` parses a file, prints frames at `-t` (default 4 seconds) and at time 0, reports
active or done, and optionally the fallback frame.

```
cd go
go run ./examples/render            # default -t 4: text visible
go run ./examples/render -t 0.5
go run ./examples/render -t 0.5 -fallback -color
go run ./examples/render -f ../examples/text.mdgl
go run ./examples/render -invalid        # shows a source-located diagnostic
```

`-invalid` is a demonstration that expects a diagnostic, so it exits 0. Invalid input given with
`-f` (or a missing file) exits nonzero (1).

## Command line

```
mdgl check FILE
mdgl frames FILE --at 0,0.5,1
mdgl play FILE
```

## Conformance

`cmd/conformance` is a headless adapter for the observable conformance
protocol. From the `v/mdgl` checkout, build it and run the runner:

```
cd go && go build -o <out>/mdgl-conformance ./cmd/conformance && cd ..
python3 scripts/conformance-runner.py --adapter '<out>/mdgl-conformance'
```

## More

- [Language specification](../SPEC.md)
- [Conformance protocol](../conformance/PROTOCOL.md)
- [Interoperability and registration roadmap (RFC 0001)](../rfcs/0001-mdgl-interoperability-and-registration-roadmap.md)
- [Adopter guide](../docs/ADOPTER-GUIDE.md)

## Status

Go is the only published full implementation of MDGL. Rendering is to terminal
cells only; a browser renderer is future work.
