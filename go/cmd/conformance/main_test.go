package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"strings"
	"testing"
)

const staticSource = "scene width=4 height=1 fallback=end\nactor a = text(\"A\") at (0,0) color=red\n"

func requestJSON(source, timeNS, extra string) []byte {
	return []byte(fmt.Sprintf(`{"v":1,"id":"test","op":"frame","source":%q,"time_ns":%s,"width":4,"height":1%s}`, source, timeNS, extra))
}

func decodeResponse(t *testing.T, raw []byte) map[string]any {
	t.Helper()
	var result map[string]any
	if err := json.Unmarshal(raw, &result); err != nil {
		t.Fatalf("decode response: %v: %s", err, raw)
	}
	return result
}

func TestExactSafeIntegerTimeNS(t *testing.T) {
	for _, input := range []struct {
		literal string
		want    int64
	}{{"1.0", 1}, {"1e9", 1_000_000_000}, {"9007199254740991", maxSafeInteger}, {"0e999999", 0}, {"0e2147483648", 0}, {"-0e2147483648", 0}, {"-0", 0}, {"-0.0", 0}} {
		got, ok := safeInteger(json.Number(input.literal))
		if !ok || got != input.want {
			t.Errorf("safeInteger(%s) = %d, %v; want %d, true", input.literal, got, ok, input.want)
		}
	}
	for _, input := range []string{"1.5", "9007199254740991.1", "9007199254740992", "-1", "1e-1", "1e-100", "1e2147483648", "1e-2147483649"} {
		if got, ok := safeInteger(json.Number(input)); ok {
			t.Errorf("safeInteger(%s) unexpectedly accepted as %d", input, got)
		}
	}
}

func TestFrameCellsColorsAndDone(t *testing.T) {
	result := process(requestJSON(staticSource, "1.0", ""))
	if !result.OK || result.Done == nil || !*result.Done {
		t.Fatalf("static frame response = %+v", result)
	}
	if result.Width != 4 || result.Height != 1 || len(result.Cells) != 1 || len(result.Cells[0]) != 4 {
		t.Fatalf("frame dimensions = %dx%d cells=%v", result.Width, result.Height, result.Cells)
	}
	if got := result.Cells[0][0]; got.Rune != "A" || got.FG != "red" || got.BG != "" {
		t.Fatalf("painted cell = %+v", got)
	}
	if got := result.Cells[0][1]; got.Rune != " " || got.FG != "normal" || got.BG != "" {
		t.Fatalf("blank cell = %+v", got)
	}

	timed := strings.Replace(staticSource, "actor a = text", "actor a = text", 1) + "@0: a.fade(in,dur=2)\n"
	before := process(requestJSON(timed, "1999999999", ""))
	atBoundary := process(requestJSON(timed, "2000000000", ""))
	if before.Done == nil || *before.Done {
		t.Fatalf("before finite end done = %v", before.Done)
	}
	if atBoundary.Done == nil || !*atBoundary.Done {
		t.Fatalf("at finite end done = %v", atBoundary.Done)
	}
}

func TestFallbackOmitsDoneAndIgnoresTime(t *testing.T) {
	result := process([]byte(fmt.Sprintf(`{"v":1,"id":"f","op":"frame","source":%q,"width":4,"height":1,"fallback":true,"time_ns":"ignored"}`, staticSource)))
	if !result.OK || result.Done != nil {
		t.Fatalf("fallback response = %+v", result)
	}
	raw, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(raw), `"done"`) {
		t.Fatalf("fallback JSON contains done: %s", raw)
	}
}

func TestCheckReturnsSourceLocatedFirstDiagnostic(t *testing.T) {
	source := "scene width=8 height=1 fallback=end\nactor a = text(\"é\") $\n"
	raw := []byte(fmt.Sprintf(`{"v":1,"id":"diag","op":"check","source":%q}`, source))
	result := process(raw)
	if !result.OK || result.Diagnostics == nil || len(*result.Diagnostics) == 0 {
		t.Fatalf("check response = %+v", result)
	}
	if got := (*result.Diagnostics)[0]; got.Line != 2 || got.Col != 22 || got.Message != `unexpected character "$"` {
		t.Fatalf("diagnostic = %+v", got)
	}
	encoded, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(encoded), `"diagnostics":[`) {
		t.Fatalf("empty diagnostic response shape missing array: %s", encoded)
	}
}

func TestBadRequestsAndVersionOrdering(t *testing.T) {
	for _, raw := range []string{
		`{"v":1,"id":"x","op":"frame","source":"x","time_ns":9007199254740991.1,"width":1,"height":1}`,
		`{"v":1,"id":"x","op":"check","source":"x\uD800"}`,
		`{"v":1,"v":1,"id":"x","op":"check","source":""}`,
		`{"v":1,"id":"x","op":"check","source":""} true`,
		`[]`,
	} {
		result := process([]byte(raw))
		if result.OK || result.Error == nil || result.Error.Code != "bad_request" {
			t.Errorf("process(%s) = %+v; want bad_request", raw, result)
		}
	}
	unsupported := process([]byte(`{"v":2,"id":"x","op":"check","source":""}`))
	if unsupported.Error == nil || unsupported.Error.Code != "unsupported_version" || unsupported.ID != "x" {
		t.Fatalf("unsupported version = %+v", unsupported)
	}
	if oneDecimal, ok := isOneInteger(json.Number("1.0")); !ok || !oneDecimal {
		t.Fatalf("v=1.0 should be mathematical integer one: %v %v", oneDecimal, ok)
	}
}

func TestServeProcessesFinalUnterminatedLine(t *testing.T) {
	input := string(requestJSON(staticSource, "0", ""))
	var output strings.Builder
	if err := serve(strings.NewReader(input), &output); err != nil {
		t.Fatal(err)
	}
	scanner := bufio.NewScanner(strings.NewReader(output.String()))
	if !scanner.Scan() {
		t.Fatalf("missing response: %q", output.String())
	}
	if result := decodeResponse(t, scanner.Bytes()); result["ok"] != true {
		t.Fatalf("final response = %v", result)
	}
	if scanner.Scan() {
		t.Fatalf("unexpected extra response: %q", scanner.Text())
	}
	if err := scanner.Err(); err != nil {
		t.Fatal(err)
	}
}

func TestServeDiscardsOversizedLineAndContinues(t *testing.T) {
	input := strings.Repeat(" ", maxLineBytes+1) + "\n" + string(requestJSON(staticSource, "0", "")) + "\n"
	var output strings.Builder
	if err := serve(strings.NewReader(input), &output); err != nil {
		t.Fatal(err)
	}
	scanner := bufio.NewScanner(strings.NewReader(output.String()))
	if !scanner.Scan() {
		t.Fatal("missing oversized-line response")
	}
	if result := decodeResponse(t, scanner.Bytes()); result["error"].(map[string]any)["code"] != "bad_request" {
		t.Fatalf("oversized-line response = %v", result)
	}
	if !scanner.Scan() {
		t.Fatal("adapter did not continue after oversized line")
	}
	if result := decodeResponse(t, scanner.Bytes()); result["ok"] != true {
		t.Fatalf("following response = %v", result)
	}
	if scanner.Scan() {
		t.Fatalf("unexpected response after second request: %s", scanner.Text())
	}
}
