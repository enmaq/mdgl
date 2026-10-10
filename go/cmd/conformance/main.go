// Command conformance is a headless newline-delimited JSON adapter for the
// shared MDGL observable conformance protocol.
package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
	"unicode/utf8"

	mdgl "github.com/enmaq/mdgl/go"
)

const maxLineBytes = 2_097_152
const maxSafeInteger int64 = 9_007_199_254_740_991

type response struct {
	V           int               `json:"v"`
	ID          any               `json:"id"`
	OK          bool              `json:"ok"`
	Diagnostics *[]wireDiagnostic `json:"diagnostics,omitempty"`
	Width       int               `json:"width,omitempty"`
	Height      int               `json:"height,omitempty"`
	Cells       [][]wireCell      `json:"cells,omitempty"`
	Done        *bool             `json:"done,omitempty"`
	Error       *wireError        `json:"error,omitempty"`
}

type wireDiagnostic struct {
	Line    int    `json:"line"`
	Col     int    `json:"col"`
	Message string `json:"message"`
}

type wireCell struct {
	Rune string `json:"r"`
	FG   string `json:"fg"`
	BG   string `json:"bg"`
}

type wireError struct {
	Code        string           `json:"code"`
	Message     string           `json:"message"`
	Diagnostics []wireDiagnostic `json:"diagnostics,omitempty"`
}

func main() {
	if err := serve(os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func serve(input io.Reader, output io.Writer) error {
	reader := bufio.NewReaderSize(input, 32*1024)
	writer := bufio.NewWriter(output)
	for {
		line, present, tooLong, err := readLine(reader, maxLineBytes)
		if err != nil && !errors.Is(err, io.EOF) {
			return err
		}
		if !present {
			return writer.Flush()
		}
		var result response
		if tooLong {
			result = failure(nil, "bad_request", "request line exceeds 2097152 bytes", nil)
		} else {
			result = safeProcess(line)
		}
		encoded, encodeErr := json.Marshal(result)
		if encodeErr != nil {
			return encodeErr
		}
		if _, err := writer.Write(encoded); err != nil {
			return err
		}
		if err := writer.WriteByte('\n'); err != nil {
			return err
		}
		if err := writer.Flush(); err != nil {
			return err
		}
		if errors.Is(err, io.EOF) {
			return nil
		}
	}
}

func readLine(reader *bufio.Reader, limit int) ([]byte, bool, bool, error) {
	line := make([]byte, 0, 4096)
	tooLong := false
	present := false
	for {
		part, err := reader.ReadSlice('\n')
		if len(part) > 0 {
			present = true
			ended := part[len(part)-1] == '\n'
			if ended {
				part = part[:len(part)-1]
			}
			if !tooLong {
				if len(line)+len(part) > limit {
					tooLong = true
					line = nil
				} else {
					line = append(line, part...)
				}
			}
			if ended {
				return line, true, tooLong, nil
			}
		}
		if errors.Is(err, bufio.ErrBufferFull) {
			continue
		}
		if errors.Is(err, io.EOF) {
			return line, present, tooLong, io.EOF
		}
		if err != nil {
			return line, present, tooLong, err
		}
	}
}

func safeProcess(line []byte) (out response) {
	defer func() {
		if recover() != nil {
			out = failure(nil, "internal", "adapter internal error", nil)
		}
	}()
	return process(line)
}

func process(line []byte) response {
	if len(bytes.TrimSpace(line)) == 0 || !utf8.Valid(line) || !validSurrogateEscapes(line) {
		return failure(nil, "bad_request", "malformed JSON request", nil)
	}
	value, err := parseStrictJSON(line)
	if err != nil {
		return failure(nil, "bad_request", "malformed JSON request", nil)
	}
	fields, ok := value.(map[string]any)
	if !ok {
		return failure(nil, "bad_request", "request must be a JSON object", nil)
	}
	id, idOK := fields["id"].(string)
	var responseID any
	if idOK {
		responseID = id
	}

	v, exists := fields["v"]
	if !exists {
		return failure(responseID, "bad_request", "missing or invalid version", nil)
	}
	isOne, validVersion := isOneInteger(v)
	if !validVersion {
		return failure(responseID, "bad_request", "missing or invalid version", nil)
	}
	if !isOne {
		return failure(responseID, "unsupported_version", "unsupported protocol version", nil)
	}
	op, ok := fields["op"].(string)
	if !ok || (op != "check" && op != "frame") {
		return failure(responseID, "bad_request", "missing or invalid operation", nil)
	}
	if !idOK {
		return failure(nil, "bad_request", "missing or invalid id", nil)
	}
	source, sourceOK := fields["source"].(string)
	if !sourceOK {
		return failure(responseID, "bad_request", "missing or invalid source", nil)
	}

	if op == "check" {
		_, diags := mdgl.Parse(source)
		encoded := encodeDiagnostics(diags)
		return response{V: 1, ID: responseID, OK: true, Diagnostics: &encoded}
	}

	fallback := false
	if raw, present := fields["fallback"]; present {
		var boolOK bool
		fallback, boolOK = raw.(bool)
		if !boolOK {
			return failure(responseID, "bad_request", "fallback must be a boolean", nil)
		}
	}
	width, widthOK := boundedInteger(fields["width"], 1, 200)
	height, heightOK := boundedInteger(fields["height"], 1, 60)
	if !widthOK || !heightOK {
		return failure(responseID, "bad_request", "width or height is missing or out of range", nil)
	}
	timeNS := int64(0)
	if !fallback {
		timeNS, ok = safeInteger(fields["time_ns"])
		if !ok {
			return failure(responseID, "bad_request", "time_ns must be an integer from 0 through 9007199254740991", nil)
		}
	}

	scene, diags := mdgl.Parse(source)
	if len(diags) > 0 || scene == nil {
		return failure(responseID, "invalid_source", "source has diagnostics", encodeDiagnostics(diags))
	}
	var cells mdgl.Cells
	var done *bool
	if fallback {
		cells = scene.FallbackFrame(width, height)
	} else {
		var finished bool
		cells, finished = scene.FrameWithDone(float64(timeNS)/1e9, width, height)
		done = &finished
	}
	rows := make([][]wireCell, len(cells))
	for y, row := range cells {
		rows[y] = make([]wireCell, len(row))
		for x, cell := range row {
			rows[y][x] = wireCell{Rune: string(cell.Rune), FG: cell.Color, BG: cell.Background}
		}
	}
	return response{V: 1, ID: responseID, OK: true, Width: len(rows[0]), Height: len(rows), Cells: rows, Done: done}
}

func failure(id any, code, message string, diags []wireDiagnostic) response {
	return response{V: 1, ID: id, OK: false, Error: &wireError{Code: code, Message: message, Diagnostics: diags}}
}

func encodeDiagnostics(diags []mdgl.Diag) []wireDiagnostic {
	out := make([]wireDiagnostic, len(diags))
	for i, diag := range diags {
		out[i] = wireDiagnostic{Line: diag.Line, Col: diag.Col, Message: diag.Message}
	}
	return out
}

func parseStrictJSON(line []byte) (any, error) {
	decoder := json.NewDecoder(bytes.NewReader(line))
	decoder.UseNumber()
	value, err := readJSONValue(decoder)
	if err != nil {
		return nil, err
	}
	if _, err := decoder.Token(); !errors.Is(err, io.EOF) {
		if err == nil {
			return nil, errors.New("trailing JSON value")
		}
		return nil, err
	}
	return value, nil
}

func readJSONValue(decoder *json.Decoder) (any, error) {
	token, err := decoder.Token()
	if err != nil {
		return nil, err
	}
	delim, composite := token.(json.Delim)
	if !composite {
		return token, nil
	}
	switch delim {
	case '{':
		object := make(map[string]any)
		for decoder.More() {
			keyToken, err := decoder.Token()
			if err != nil {
				return nil, err
			}
			key, ok := keyToken.(string)
			if !ok {
				return nil, errors.New("object key is not a string")
			}
			if _, exists := object[key]; exists {
				return nil, errors.New("duplicate object key")
			}
			value, err := readJSONValue(decoder)
			if err != nil {
				return nil, err
			}
			object[key] = value
		}
		_, err := decoder.Token()
		return object, err
	case '[':
		for decoder.More() {
			if _, err := readJSONValue(decoder); err != nil {
				return nil, err
			}
		}
		_, err := decoder.Token()
		return []any{}, err
	default:
		return nil, errors.New("unexpected JSON delimiter")
	}
}

func validSurrogateEscapes(data []byte) bool {
	inString := false
	for i := 0; i < len(data); i++ {
		if !inString {
			if data[i] == '"' {
				inString = true
			}
			continue
		}
		if data[i] == '"' {
			inString = false
			continue
		}
		if data[i] != '\\' {
			continue
		}
		if i+1 >= len(data) {
			return false
		}
		if data[i+1] != 'u' {
			i++
			continue
		}
		code, ok := hex4(data[i+2:])
		if !ok {
			return false
		}
		switch {
		case code >= 0xD800 && code <= 0xDBFF:
			if i+12 > len(data) || data[i+6] != '\\' || data[i+7] != 'u' {
				return false
			}
			low, ok := hex4(data[i+8:])
			if !ok || low < 0xDC00 || low > 0xDFFF {
				return false
			}
			i += 11
		case code >= 0xDC00 && code <= 0xDFFF:
			return false
		default:
			i += 5
		}
	}
	return !inString
}

func hex4(data []byte) (uint16, bool) {
	if len(data) < 6 {
		return 0, false
	}
	var value uint16
	for _, b := range data[2:6] {
		value <<= 4
		switch {
		case b >= '0' && b <= '9':
			value += uint16(b - '0')
		case b >= 'a' && b <= 'f':
			value += uint16(b-'a') + 10
		case b >= 'A' && b <= 'F':
			value += uint16(b-'A') + 10
		default:
			return 0, false
		}
	}
	return value, true
}

func isOneInteger(value any) (bool, bool) {
	number, ok := value.(json.Number)
	if !ok {
		return false, false
	}
	s := string(number)
	negative := strings.HasPrefix(s, "-")
	if negative {
		s = s[1:]
	}
	exponent := int64(0)
	if index := strings.IndexAny(s, "eE"); index >= 0 {
		exp, err := strconv.ParseInt(s[index+1:], 10, 32)
		if err != nil {
			return false, false
		}
		exponent = exp
		s = s[:index]
	}
	whole, fraction := s, ""
	if index := strings.IndexByte(s, '.'); index >= 0 {
		whole, fraction = s[:index], s[index+1:]
	}
	digits := strings.TrimLeft(whole+fraction, "0")
	if digits == "" {
		return false, true
	}
	shift := exponent - int64(len(fraction))
	if shift < 0 {
		remove := -shift
		if remove >= int64(len(digits)) || strings.Trim(digits[len(digits)-int(remove):], "0") != "" {
			return false, false
		}
		digits = digits[:len(digits)-int(remove)]
		shift = 0
	}
	return !negative && digits == "1" && shift == 0, true
}

func boundedInteger(value any, minimum, maximum int64) (int, bool) {
	result, ok := safeInteger(value)
	if !ok || result < minimum || result > maximum {
		return 0, false
	}
	return int(result), true
}

func safeInteger(value any) (int64, bool) {
	number, ok := value.(json.Number)
	if !ok {
		return 0, false
	}
	s := string(number)
	negative := false
	if strings.HasPrefix(s, "-") {
		negative = true
		s = s[1:]
	}
	exponentText := "0"
	if index := strings.IndexAny(s, "eE"); index >= 0 {
		exponentText = s[index+1:]
		s = s[:index]
	}
	whole, fraction := s, ""
	if index := strings.IndexByte(s, '.'); index >= 0 {
		whole, fraction = s[:index], s[index+1:]
	}
	digits := strings.TrimLeft(whole+fraction, "0")
	if digits == "" {
		return 0, true
	}
	exponent, err := strconv.ParseInt(exponentText, 10, 32)
	if err != nil {
		return 0, false
	}
	shift := exponent - int64(len(fraction))
	if shift < 0 {
		remove := -shift
		if remove >= int64(len(digits)) || strings.Trim(digits[len(digits)-int(remove):], "0") != "" {
			return 0, false
		}
		digits = digits[:len(digits)-int(remove)]
		shift = 0
	}
	if negative || digits == "" || int64(len(digits))+shift > 16 || shift > 16 {
		return 0, false
	}
	result, err := strconv.ParseInt(digits, 10, 64)
	if err != nil {
		return 0, false
	}
	for i := int64(0); i < shift; i++ {
		result *= 10
	}
	if result > maxSafeInteger {
		return 0, false
	}
	return result, true
}
