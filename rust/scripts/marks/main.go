package main

import (
	"fmt"
	"unicode"
)

func main() {
	fmt.Println("//V", unicode.Version)
	start := rune(-1)
	for r := rune(0); r <= 0x110000; r++ {
		in := r <= 0x10FFFF && unicode.IsMark(r)
		if in && start < 0 {
			start = r
		}
		if !in && start >= 0 {
			fmt.Printf("%X %X\n", start, r-1)
			start = -1
		}
	}
}
