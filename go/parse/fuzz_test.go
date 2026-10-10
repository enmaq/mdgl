package parse

import (
	"os"
	"path/filepath"
	"testing"
)

func FuzzParse(f *testing.F) {
	f.Add("")
	f.Add("scene width=10 height=4 fallback=end\nactor a = text(\"hi\") at (0,0)\n")
	f.Add("actor a = text(\"\\\") at (((\n")
	paths, _ := filepath.Glob("../../conformance/*.mdgl")
	for _, path := range paths {
		data, err := os.ReadFile(path)
		if err == nil {
			f.Add(string(data))
		}
	}
	f.Fuzz(func(t *testing.T, source string) { _, _ = Parse(source) })
}
