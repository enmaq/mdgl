//go:build ignore

// gen_cat prints C range tables for Go's unicode.IsMark (Mn|Mc|Me) and unicode.IsPrint, the exact
// predicates the Go reference uses (model.Glyphs, strconv.Quote). Go's tables are Unicode 15.0.0.
package main

import (
	"fmt"
	"unicode"
)

func emit(name string, pred func(rune) bool) {
	fmt.Printf("static const struct { uint32_t lo, hi; } %s[] = {\n", name)
	n := 0
	for r := rune(0); r <= unicode.MaxRune; {
		if !pred(r) {
			r++
			continue
		}
		s := r
		for r <= unicode.MaxRune && pred(r) {
			r++
		}
		fmt.Printf("{0x%X,0x%X},", s, r-1)
		if n++; n%8 == 0 {
			fmt.Println()
		}
	}
	fmt.Println("\n};")
}

func main() {
	emit("mark_table", unicode.IsMark)
	emit("print_table", unicode.IsPrint)
}
