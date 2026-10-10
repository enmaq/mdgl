# Third-party notices

`mdgl_unicode.h` contains property tables derived from **github.com/rivo/uniseg v0.4.7**
(Unicode 15.0.0 grapheme-break, East Asian Width and emoji-presentation data), and range tables
produced by Go's standard `unicode` package (`IsMark`, `IsPrint`; Go is BSD-3-Clause,
(c) The Go Authors). Unicode data files are under the Unicode License
(https://www.unicode.org/license.html). The grapheme-step algorithm in `mdgl.c` is a port of
uniseg's `grapheme*`/`step`/`width` logic.

## uniseg (MIT License)

MIT License

Copyright (c) 2019 Oliver Kuederle

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
