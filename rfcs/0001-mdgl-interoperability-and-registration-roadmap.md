# RFC 0001: MDGL interoperability, conformance evidence and an optional registration roadmap

Project RFC draft, number 0001 in this repository's `rfcs/NNNN-title.md` series
(see [CONTRIBUTING.md](../CONTRIBUTING.md)). The number is a local sequence number only.

## Status of This Memo

This is a **project draft** of the MDGL project. It is **not** an IETF document, **not** an RFC and **not** an
RFC Editor publication; no standards body has reviewed, adopted or endorsed it. The RFC-like layout is a
presentation choice. MDGL is not 1.0: it is 0.x and unstable ([README.md](../README.md)).
[SPEC.md](../SPEC.md) remains the **only normative text**; where this draft and `SPEC.md` differ, `SPEC.md` wins.
This draft adds no normative decision. Every item labelled **PROPOSAL** or listed in section 10 is an open
question, not an accepted rule. Review status: Reviewed for factual consistency (independent review and a maintainer review pass); remains an unadopted project proposal; not an IETF, RFC Editor or IANA document or endorsement; SPEC.md remains authoritative; no normative adoption is implied by the reviews. The circle clarification is a SPEC.md change made by the project maintainers, not by the review.

Labels: **[SPEC]** restates `SPEC.md`; **[PROTOCOL]** restates [conformance/PROTOCOL.md](../conformance/PROTOCOL.md);
**[PROFILE]** restates the non-normative [reference profile](../conformance/REFERENCE_PROFILE.md) or behaviour
observed in the adapters' sources; **[INFORMATIVE]** explains; **[PROPOSAL]** is not an accepted rule.
Paths are relative to the MDGL project directory (this file's links are rebased for `rfcs/`).

## Abstract

MDGL (MarkdownGL) is a small, line-based animation language for a Markdown fence labelled `mdgl`. This draft
records, as of 2026-10-10 UTC, the interoperability evidence gathered with the project's language-neutral
conformance suite, the limits of that evidence, the open specification questions, and an optional, future,
unregistered roadmap towards a vendor-tree media type. It requests no IANA or IETF action.

## 1. Introduction

MDGL scenes declare a stage, actors (`text`, `rect`, `circle`, wire `cube`) and timed actions. A frame is a pure
function of (scene, time, size). The project's position is that the specification plus a conformance suite is the
product ([CONTRIBUTING.md](../CONTRIBUTING.md)); implementations come and go. The CommonMark specification is a
useful structural model: versioned text whose examples double as conformance tests
([spec.commonmark.org](https://spec.commonmark.org/)).

Standards context, for orientation only. [RFC 7763](https://www.rfc-editor.org/info/rfc7763/) registers the
`text/markdown` media type; it is an Informational RFC in the IETF stream (it is not an Independent Submission).
Its section 6.1 creates the "Markdown Variants" registry. [RFC 7764](https://www.rfc-editor.org/rfc/rfc7764) is the
companion document with guidance and initial variant registrations. Neither defines a Markdown grammar; CommonMark's
specification is separate. MDGL is not a Markdown variant: it is a language embedded in a Markdown fence. The
fence label `mdgl` has no IANA registry.

## 2. Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED",
"NOT RECOMMENDED", "MAY" and "OPTIONAL" are to be interpreted as in BCP 14
([RFC 2119](https://www.rfc-editor.org/rfc/rfc2119), [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)) when, and
only when, they appear in all capitals. `SPEC.md` mostly states rules in plain present tense; those statements are
normative there regardless. Here, capitalised keywords appear only where a rule is restated or a proposal is marked,
and a proposal binds nobody. Sections are labelled normative-restatement, informative or proposal in their text.

## 3. Language definition (by reference)

The language is defined by [SPEC.md](../SPEC.md) (grammar 0.1). Its EBNF is the `ebnf` block in the section
"Grammar" of `SPEC.md`; it is not copied here, so it cannot drift. The authoring primer is [MDGL.md](../MDGL.md).
Reserved vocabulary (cameras, lights, meshes, materials, three.js import, cells references, solid faces, `def`,
`seq`, images, paths) is not accepted 0.1 syntax [SPEC]. Only one renderer profile exists, terminal cells with
braille dots; a browser renderer is not shipped.

## 4. Interoperability and conformance

### 4.1 Components [PROTOCOL]

(a) the legacy corpus (`NAME.mdgl` with `NAME.expect` or `NAME.err`); (b) observable fixtures
`conformance/observable/obs_*.obs.json` with a mandatory hand-derived `derivation`; (c) wire protocol v1
(newline-delimited JSON, ops `check` and `frame`, [schema](../conformance/protocol.schema.json)); (d) the runner.
Command, from the MDGL project directory:

    python3 scripts/conformance-runner.py --adapter '<cmd>'

The corpus has 86 fixtures: 46 legacy + 40 observable, of which 64 are normative and 22 are non-normative
(assumption-labelled, fallback-cube, reference-profile or circle-reject). Expectations are hand-derived from SPEC, not generated
from any implementation.

### 4.2 Evidence as of 2026-10-10 UTC [INFORMATIVE]

In the final integration all five adapters (Go, Rust, C, TypeScript compiled to JavaScript, Python) pass the
83-fixture corpus, 83/83 = 63 normative + 20 non-normative, under the bounded protocol-v1 profile. This is
**bounded evidence, not a universal SPEC certification**: it shows that five independently written code bases agree
with hand-derived expectations on this corpus, nothing more. The 20 non-normative passes are
"assumption-based pass (not certification)" by the runner's own wording.

Record of the accepted final proof (short prefixes): original proof archive sha256 `69115bce...`, with the corrected
TypeScript result sha256 `7c38eb74...`; new code source seal (320 members) sha256 `a5b0c398...`, sealed at 18:44 UTC.
The TypeScript run covered 10 targeted tests, raw malformed and valid UTF-8 requests, and parser, frame, fallback
and TypeScript type-declaration checks of the npm-installed package; the Python run covered parser and frame checks of the installed
wheel. All actual archives and the exact public source passed the project's release privacy gate.

Dated finding (2026-10-10 UTC): during final integration the TypeScript adapter accepted a request containing
invalid UTF-8, where protocol v1 requires rejection. It was **fixed** and **independently verified** by the final
retry.

Corpus note: the 83/83 result above was recorded before the three circle boundary fixtures were added (section 4.4
item 5). The corpus now has 86 fixtures = 46 legacy + 40 observable; 64 normative + 22 non-normative. No full pass
of the 86-fixture corpus is claimed here: independent verification of the full 86-fixture corpus is pending.

Not covered: the normative fixtures do not include normative rect, circle or coloured-cube rasterisation
(section 10, item 1); the C locale limitation below; any behaviour outside the corpus.

### 4.3 What is published [INFORMATIVE]

Only Go is a published full implementation (module `github.com/enmaq/mdgl/go`, tags `v0.2.0` and `go/v0.2.0`).
The published npm `@enmaq/mdgl`, crates.io `mdgl` and PyPI `mdgl` 0.2.0 packages remain limited header/resource seed
checks. The current Rust, C, TypeScript and Python cores and adapters are **unreleased** (`VERSION` is still
0.2.0). JavaScript is the compiled TypeScript: one implementation, one npm package.

Known C limitation: the C library builds with `_GNU_SOURCE` (for `M_PI`), and its locale-dependent test
(`c/test_locale.c`, run with `de_DE.UTF-8`) is **skipped** (exit 77) when that locale is not installed, so the
comma-decimal path is not exercised on such hosts. Windows/MSVC is untested ([c/README.md](../c/README.md)).

### 4.4 Reference-profile facts and their Unicode context [PROFILE, non-normative]

The following are behaviours of the reference profile and of the adapters' sources. None is adopted as a
normative rule; each is a candidate for a SPEC change (section 10). They are kept strictly separate:

1. **Unicode 15 grapheme and width behaviour of the adapters.** The adapters segment extended grapheme clusters
   (UAX #29) and compute cluster width with Unicode 15.0.0 data, reproducing the Go reference's dependency
   (rivo/uniseg v0.4.7: rules GB1-GB13, no Unicode 15.1 GB9c rule). Cluster width is not only East Asian Width: for
   example, Regional Indicators count as two cells, Extended_Pictographic as one plus Emoji_Presentation, and
   U+FE0E/U+FE0F adjust an emoji's width. A cluster wider than one cell is emitted as U+FFFD.
2. **A separate proposal:** define "wide" as East Asian Width `W` or `F` only (local assumption A4 in PROTOCOL.md).
   This is **not** what the profile does, is not a SPEC rule, and would need fixtures if adopted.
3. **Text reveal.** The number of revealed cells is `floor(maxWidth * reveal + 1e-9)`: an epsilon added to the
   product before the floor. It is not a "clip tolerance". SPEC states no such epsilon; this is an open gap.
4. **Raster reveal.** For `rect` and `circle`, a painted cell is revealed while its column centre is within
   `x + width * scale * reveal`, where `x` is the **untransformed** actor X; parent transform and rotation are
   ignored. SPEC's "reveal is inherited" sentence is unresolved against this (open gap).
5. **Geometry.** Line sampling uses at most 800 steps; a circle is a closed polyline of 720 chords; the maximum
   circle size follows the SPEC.md clarification (see below). rect and circle use no 0.5 dot offset,
   while the cube keeps the SPEC offset ([REFERENCE_PROFILE.md](../conformance/REFERENCE_PROFILE.md) sections 1 and 5).

   *Circle bound (resolved by project decision).* The maximum circle size is radius <= 100,
   equivalently diameter <= 200: `circle(r)` with 0 < r <= 100 is valid and r > 100 is an error. This is a SPEC.md
   clarification (one sentence) made by the project maintainers; it was not made by this review, and it is not an
   IETF, RFC Editor or other standards-body decision. SPEC.md remains authoritative. It is a compatibility
   interpretation: by static reading of the adapter sources, the Go, Rust, C and Python adapters already reject a
   radius greater than 100, so the clarification preserves them. The TypeScript adapter earlier accepted a radius up to 200;
   its owner has since corrected it, and its diagnostic now reads exactly `circle radius must be positive and <=100`,
   identical to Go, Rust, C and Python. Three cross-language boundary fixtures exist (`obs_circle_r100_accept`
   normative; `obs_circle_r101_reject` and `obs_circle_r0_reject` non-normative, ASSUMES G4). The circle bound
   clarification (radius <= 100 / diameter <= 200) is confirmed by the five adapters on the three circle boundary
   fixtures (targeted run); independent verification of the full 86-fixture corpus is pending. SPEC does not pin the
   diagnostic wording or position, so the agreement on wording is an observation, not a SPEC rule. The 83-fixture
   results in section 4.2 were recorded before these fixtures.

## 5. Security considerations [SPEC unless marked]

- Scenes may come from untrusted authors, including LLMs. Input beyond the SPEC limits (256 KiB input, 16 KiB line,
  200x60 stage, 64 actors, 1024 actions, 1024 graphemes, 60 s, fps 1..30, repeat 1..1000 or infinite) is rejected
  before play; rejected input never plays. Implementations SHOULD still apply their own time and memory limits
  [INFORMATIVE]; SPEC states none beyond these.
- The evaluator is pure and does no I/O; there is no background scheduler; the reserved three.js import performs
  no loading in 0.1. Control characters, tabs and newlines in text and title are rejected and cell content carries
  no terminal control sequences; only the optional player emits control sequences (DEC mode 2026).
- No clock, randomness or host state in frames; seeking is pure. Redirected output and reduced motion use the
  fallback frame with no timer.
- [PROTOCOL] Adapters ignore environment, keep no state between requests, treat stderr as logs, and reject invalid
  UTF-8 in requests (the dated TypeScript finding in 4.2 concerned exactly this). The request line limit is
  2 097 152 bytes.
- Archives and source are checked by the project's release privacy gate (`scripts/check-release-privacy.py`)
  before publication; that gate is a hygiene check, not a security audit.

## 6. Compatibility and versioning [INFORMATIVE]

The `mdgl 0.1` header is the grammar version defined by `SPEC.md`. The package `VERSION` (currently 0.2.0) is
separate and does not change the grammar version. At 0.x only the latest minor is supported; there is no
deprecation or ABI/API stability promise before 1.0 ([README.md](../README.md), [CHANGELOG.md](../CHANGELOG.md)).
Syntax changes go through an RFC in `rfcs/NNNN-title.md` ([CONTRIBUTING.md](../CONTRIBUTING.md)). Unknown scene keys
are errors; unknown wire-request fields are ignored. `SPEC.md` states no extension namespacing.

## 7. Registration roadmap (informative, FUTURE and OPTIONAL)

Nothing in this section has been done, requested or decided. No standards body has approved anything.

- **Candidate name:** `text/vnd.enmaq.mdgl`. It is **unregistered**. Its suitability is subject to review by the
  registration authority. The vendor tree is described in
  [RFC 6838 section 3.2](https://www.rfc-editor.org/rfc/rfc6838.html#section-3.2): it is for media types associated
  with publicly available products, and a registration belongs properly to the vendor or organisation producing the
  product.
- **Change controller:** the author/ENMAQ, as RFC 6838 requires a named change controller for a registration. MDGL
  was created and is maintained by Victor Brunko ([AUTHORS](../AUTHORS)). This makes no claim of exclusive
  ownership, and no claim of trademark, registration or submission.
- **Mechanism, if ever pursued:** the IANA application form,
  [iana.org/form/media-types](https://www.iana.org/form/media-types), after the specification and a second
  independent implementation are stable. The form's own instructions govern, not this draft.
- The fence label `mdgl` has no IANA registry; `text/markdown` variants are unrelated to it (section 1).

See [docs/ADOPTION-ROADMAP.md](../docs/ADOPTION-ROADMAP.md) for the ordered steps. Publishing mechanics for Internet-Draft style text are in
[docs/INTERNET-DRAFT-PUBLISHING.md](../docs/INTERNET-DRAFT-PUBLISHING.md) (maintained separately; informative only).

## 8. IANA considerations

None. This draft requests no IANA action, creates no registry, and registers no media type, file extension or
fence label.

## 9. Process fields required by CONTRIBUTING.md [INFORMATIVE]

- **Problem:** outside implementers and embedders lack one place stating what evidence exists and what does not.
- **Proposal:** adopt the CommonMark-style path (spec, examples, conformance suite, adopter guide); keep the
  registration roadmap as a later option; resolve section 10 items one by one through SPEC changes with fixtures.
- **Alternatives:** an early IETF or media-type submission (premature at 0.x with open normative gaps); no external
  documentation (leaves the gaps undiscoverable).
- **Effect on LLM authoring:** none; no syntax changes.
- **Conformance cases:** none added by this draft; section 10 lists the fixtures each proposal would need.

## 10. Open questions and proposals (NOT accepted rules)

Each item: current behaviour, then a **PROPOSAL**. No item is a SPEC rule.

1. **Rect/circle/cube-colour raster extents and offset.** SPEC fixes `2*cellX-0.5`, `4*cellY-0.5` generally but not
   the rect outline box, circle extent or sample count; the profile uses no offset for rect/circle (4.4, item 5).
   Only the three non-normative `obs_ref_*` fixtures cover them. PROPOSAL: choose one offset rule, state box and
   sampling in SPEC, then promote the fixtures.
2. **Title epsilon.** The formula in 4.4 item 3 is adapter behaviour; SPEC wording and semantics are open.
   PROPOSAL: state it numerically in SPEC or remove the term.
3. **Reveal and transform.** 4.4 item 4 versus SPEC's "reveal is inherited". PROPOSAL: one sentence plus a fixture.
4. **Easing curves.** No fixtures. PROPOSAL: fixtures at fixed progress points and a stated tolerance.
5. **Stage limits beyond 200x60.** PROPOSAL: one fixture per limit with the exact first diagnostic.
6. **Reserved-vocabulary diagnostics.** First-diagnostic text unpinned. PROPOSAL: pin a form and add fixtures.
7. **Diagnostic wording beyond the `.err` set (G4).** PROPOSAL: compare only line and column for new fixtures
   unless listed in a SPEC diagnostics table.
8. **Fallback `done` (G1).** Omitted on the wire in v1. PROPOSAL: define it or state it undefined.
9. **Viewport clamp (G2).** Response size is `min(request, scene)`. PROPOSAL: keep as protocol policy only.
10. **Blend rounding (G5).** Go rounds half away from zero. PROPOSAL: pin half-up for nonnegative channels.
11. **Extension namespacing.** Unstated. PROPOSAL: reserve hyphenated or `x-` keys, rejected unless enabled.
12. **Unicode version and "wide".** SPEC pins no Unicode version, segmentation algorithm or width definition. The
    profile uses Unicode 15.0.0 (4.4 item 1); a separate proposal would define wide as East Asian Width W/F only
    (4.4 item 2). PROPOSAL: pin a version and algorithm and decide between the two, with fixtures.
13. **Assumptions A1-A4** (type end time, wipe direction, blink half-cycles, wide meaning). PROPOSAL: promote to
    SPEC text or keep their fixtures non-normative.
14. **Circle size bound.** Resolved (project decision). The project
    maintainers clarified in SPEC.md that the maximum is radius <= 100 (diameter <= 200); see 4.4 item 5.
    Three boundary fixtures exist and the five adapters agree on them (targeted run); independent verification of
    the full 86-fixture corpus is pending. Numbering of other items is unchanged.

## 11. References

### 11.1 Normative (project)
- [SPEC.md](../SPEC.md); [conformance/PROTOCOL.md](../conformance/PROTOCOL.md) and
  [protocol.schema.json](../conformance/protocol.schema.json).
- [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119), [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) (BCP 14),
  for the keyword convention only.

### 11.2 Informative
- [conformance/README.md](../conformance/README.md), [REFERENCE_PROFILE.md](../conformance/REFERENCE_PROFILE.md),
  [CONTRIBUTING.md](../CONTRIBUTING.md), [RELEASING.md](../RELEASING.md), [CHANGELOG.md](../CHANGELOG.md),
  [README.md](../README.md), [MDGL.md](../MDGL.md), [docs/ADOPTER-GUIDE.md](../docs/ADOPTER-GUIDE.md).
- [RFC 7763](https://www.rfc-editor.org/info/rfc7763/), [RFC 7764](https://www.rfc-editor.org/rfc/rfc7764),
  [RFC 6838](https://www.rfc-editor.org/rfc/rfc6838.html#section-3.2),
  [IANA media type application](https://www.iana.org/form/media-types).
- [CommonMark specification](https://spec.commonmark.org/).

*End of draft. Reviewed for factual consistency only; not adopted.*
