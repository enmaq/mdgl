# Releasing MDGL

Pipeline: `v/infra/pipelines/cci/enmaq.yml`. Publisher: `scripts/publish-mdgl-packages.sh`
(`--check-version`, `--cohort`, `--publish`, `--out`, `--crates-owner-confirmed`,
`--pypi-owner-confirmed`). Never print or commit tokens.

## Single-version policy

`VERSION` is the only version source. Go, Rust, C, JS, TS and Python all carry the same
version; `check-version.sh` verifies that every manifest and the `CHANGELOG.md` heading agree
with `VERSION`, and `scripts/publish-mdgl-packages.sh --check-version` runs the same drift
check. CI (`packages` job) and the cohort job both run it; a release never proceeds when
`VERSION` and the manifests disagree.

- Versions follow semver. A published version is never reused or replaced: fix forward with a bump.
- Releases are `0.x`: unstable, syntax and APIs may change between minor versions.
- Bump `VERSION`, every manifest and `CHANGELOG.md` together in one commit.

## Packages

| Language | Registry / name | Manifest | Released by |
|---|---|---|---|
| JS/TS | npm `@enmaq/mdgl` | `ts/package.json` | `release-mdgl-cohort` |
| Rust | crates.io `mdgl` | `rust/Cargo.toml` | `release-mdgl-cohort` |
| Python | PyPI `mdgl` | `python/pyproject.toml` | `release-mdgl-cohort` |
| C | none (source tarball, recorded in the release record) | `c/CMakeLists.txt` | `release-mdgl-cohort` (record only) |
| Go | Go module `github.com/enmaq/mdgl/go` | `go/go.mod`; version passed to snapshot publisher | manual snapshot publisher; no registry CCI job |

## Cohort release

One CCI job, `release-mdgl-cohort` (resource `mdgl-release-git`), runs
`scripts/publish-mdgl-packages.sh --cohort` for the version in `VERSION`. It triggers on
`VERSION`, `CHANGELOG.md`, `check-version.sh`, every language dir (`go/`, `js/`, `ts/`, `rust/`,
`python/`, `c/`), the licences, `SPEC.md`, `conformance/` and the publisher script and its test.
Docs-only edits do not trigger it. Every all-language source edit, including `go/`, triggers full
validation; the release identity is `VERSION`, and changed content under an unchanged version is
refused by the publisher. A first task validates Go (`go vet`, `go build`, full `go test`
including conformance) and writes `go-validated.txt` (version and source sha256 of `go/` and
`conformance/`); the publish task requires it (`--require-go-validated`), so a failed Go
validation stops before any upload. The C test is built and run in the publish task. The job
makes no Git mutations. The actual Go release (nested tag `go/vX.Y.Z`) remains the explicit,
separate Git publisher `release-mdgl` and needs human permission. The release record (fields
`go`, `cohort`, `go_validation`) shows the cohort as `incomplete` unless the published `go/vX.Y.Z` sources are verified equal to the
candidate (`go.tag_state` is `verified-match`, checked by downloading the public tag archive and
comparing a sha256 of `go/`, `conformance/`, `SPEC.md` and `VERSION`; the `go-validated.txt` digest covers `go/` and `conformance/` only): a registry-only success, or a mere existing tag
(`absent`, `unverified`), is NOT a successful all-language release. If the tag exists with
different sources (`mismatch`) the job refuses before any upload: bump `VERSION`.

Flow:
1. Drift preflight against all manifests and `CHANGELOG.md`.
2. Build and test every artifact (npm, crate, wheel/sdist, C source tarball).
3. Run the privacy gate against staged source trees and every artifact, then preflight credentials and preconditions for ALL registries.
4. Only then upload, and only when `MDGL_PUBLISH` is `"1"` (the committed setting).

## Release privacy gate

Both release publishers use `scripts/check-release-privacy.py` before a public
snapshot push or any registry upload. It scans complete source files and archive
members without extracting archives. Unsafe archive paths, links, special members,
oversized content, credentials, private addresses/hosts/paths, and forbidden
leftovers stop the release. Findings include only a path, line number, and category;
they never include matching text or a credential hash. Available `NPM_TOKEN`,
`CARGO_REGISTRY_TOKEN`, and `PYPI_TOKEN` values are compared in memory and are
never passed to the checker as arguments.

Binary media needs a matching SHA256 entry in the privately maintained JSON review
manifest selected by `MDGL_MEDIA_REVIEW_FILE`. The manifest is kept outside the
public `v/mdgl` export. A missing entry or changed hash blocks publication until
the media has a new review. The accepted review covers all frames visually; OCR
was not performed. Do not describe it as OCR coverage.

Registries cannot be updated transactionally, so a release is **not atomic**. If an upload
fails part-way, some registries hold the new version and others do not (a partial release).
Re-running the job completes it: the script verifies that an existing version has identical
artifacts and skips it, and uploads the missing ones. A version that exists with different
content is a collision and fails; bump the version.

A push that does not change `VERSION` but touches shared source re-runs the cohort. In declared
release mode (see below) the cohort verifies and skips identical existing artifacts, and changed
content without a version bump fails and asks for a bump. While `## [Unreleased]` has content the
push routes to development mode instead, which makes no such registry comparison.

Development vs release: while `CHANGELOG.md` has any content under `## [Unreleased]` the cohort
job (`MDGL_MODE=auto`, also the script default) runs in development mode: it builds, tests and
runs the privacy gate, makes no MDGL release metadata or Go tag probes and uploads nothing
(downloading build dependencies is allowed), and records `cohort_status: development`. A release is
declared by moving the Unreleased body under a dated `## [X.Y.Z] - YYYY-MM-DD` heading (a valid
calendar date, nothing after it), equal to `VERSION`, in the commit that bumps `VERSION`; an unclear
state fails, and `MDGL_MODE=release` never overrides unreleased content.

Release record: every run writes `release-record.json` and `release-record.txt` (version,
source SHA256 manifest, artifact checksums, per-registry outcomes, Go and C entries). They
contain no secrets, are printed into the build log and are the job output `mdgl-release-out`.
The record is explicitly **unsigned**: it is a checksum ledger, not a signature, provenance
attestation or SBOM.

## Naming

Rust and PyPI keep the name `mdgl`. npm uses the scoped name `@enmaq/mdgl`: npm rejected
unscoped `mdgl` (E403, too similar to existing packages md5, mjml, madge, del). The name lives only
in `ts/package.json` (`publishConfig.access` is `public`, required for a scoped first publish); the
publisher reads it from there, encodes the scope as `@enmaq%2Fmdgl` for registry metadata URLs
(404 there means the name is free), and the tarball is `enmaq-mdgl-<version>.tgz`.

Migration note: `@wildneuro/mdgl` 0.2.0 was published first under the maintainer's personal scope
and is superseded by `@enmaq/mdgl`.

## First claim

1. Create tokens (see Tokens) and store them in the credential manager as `mdgl-npm-token`,
   `mdgl-crates-token`, `mdgl-pypi-token`.
2. Continuing releases are enabled (`MDGL_PUBLISH: "1"`): the cohort job publishes automatically when
   `VERSION` or relevant shared sources change. For a local dry run, run
   `scripts/publish-mdgl-packages.sh --cohort` without `--publish`.
3. Registry name state is rechecked automatically in the publisher preflight. Current published
   names: crates.io `mdgl`, PyPI `mdgl`, npm `@enmaq/mdgl` (all at 0.3.0; npm is scoped
   because unscoped `mdgl` was refused as too similar to existing names). Future releases bump
   `VERSION`; the cohort job skips identical existing versions.
4. Verify ownership by hand and set the attestations below.
5. Publishing stays enabled; the owner flags below remain `"0"`, so a later `VERSION` bump for
   crates.io and PyPI is refused until a human attests ownership.

Owner attestations (`MDGL_CRATES_OWNER_CONFIRMED`, `MDGL_PYPI_OWNER_CONFIRMED`, both `"0"` by
default) are statements by a human, not checks. crates.io `/api/v1/me` accepts only a browser
session cookie, so a publish token cannot query ownership. PyPI has no usable authenticated owner
check. Set `"1"` only after confirming in the web UI that the account behind the token owns the
crate/project. The final authority is the registry rejecting an upload by a non-owner.

## Tokens

npm: use a granular access token, permission Read and write, with the bypass-2FA option so
non-interactive publishing works (see docs.npmjs.com/about-access-tokens). Those docs say direct
publishing with granular tokens will be removed in January 2027, so revisit with stage-only or
trusted publishing before then. Set an expiry and rotate. The scope must allow `@enmaq/mdgl`.

crates.io: scopes `publish-new` and `publish-update`. A token limited to crate name `mdgl` is
allowed before the crate exists (source: `crates_io_database` `models/token/scopes.rs`).

PyPI: for the first upload use an account-wide token (inference from pypi.org/help#apitoken),
then create a project-scoped token for `mdgl` and revoke the account-wide one.

Concourse cannot use trusted publishing, so plain tokens are mapped as `NPM_TOKEN`,
`CARGO_REGISTRY_TOKEN` and `PYPI_TOKEN`.

### Rotation (human-driven)

With the current token-based Concourse flow, a human creates each replacement token in the
registry UI; nothing here creates or renews tokens automatically. Rotate when a token nears the
expiry chosen at creation, or to narrow scope after the first claim.

1. Create the replacement in the registry account settings, following the scope rules in Tokens
   above (npm `@enmaq/mdgl`, crates.io crate `mdgl`, PyPI project `mdgl`).
2. Install it in the private credential stash and apply it with the pipeline reconfigure step
   (operator procedure is in the private note). Never paste token values into chat or any file.
3. Revoke the OLD token only after the replacement has been applied AND authenticated, by a
   controlled release or the registry account identity/token page. A `--dry-run` or build checks
   packaging, NOT authentication.

## Rollback

- npm: `npm deprecate @enmaq/mdgl@X "reason"`; unpublish is limited.
- crates.io: `cargo yank --version X` (does not delete).
- PyPI: yank the release in the web UI.
Versions are never reusable on any registry; fix forward with a bump.

## Compatibility and support policy

At 0.x only the latest minor version is supported; there is no backport. There is no
deprecation promise before 1.0: anything may change between minor versions, recorded in
`CHANGELOG.md`. All implementations share the language contract in [`SPEC.md`](SPEC.md) and the
[`conformance/`](conformance/) suite. All five languages (Go, Rust, C, JS/TS, Python) ship an adapter and
passed the 86-fixture corpus under the bounded protocol-v1 profile (independent verification, 2026-10-10 UTC, accepted by the coordinator); this is bounded evidence, not a full-conformance claim.

Package version versus grammar version: the shared MDGL package version (`VERSION`, currently
0.3.0) is distinct from the language identifier. The `mdgl 0.1` header in a scene is the grammar
version defined by `SPEC.md`; it does not change when `VERSION` changes.

Compatibility statement: before 1.0 (0.x) there is no ABI or API stability promise in any
language. Supported builds are the ones exercised in CI (`.github/workflows/ci.yml`).

Precedents for one coordinated version plus an explicit compatibility statement (not proof that
every such project does this): protobuf shares a minor.point version across languages with
language-specific major versions and keeps spec Editions distinct from runtime versions
(https://protobuf.dev/support/version-support/); GraalVM publishes component compatibility and
release notes (https://docs.oracle.com/en/graalvm/jdk/25/docs/release-notes/); folly states no
commit-to-commit ABI guarantee and lists supported builds and platforms
(https://github.com/facebook/folly/blob/main/README.md).

## Go snapshot release
The public repository receives a snapshot of the full `v/mdgl` tree, including the Go module,
other language folders, documentation, and shared conformance assets. Each coordinated release
X.Y.Z uses the shared version from `VERSION` and requires a matching `## [X.Y.Z]` heading in
the root `CHANGELOG.md`. The publisher creates matching `vX.Y.Z` (snapshot) and `go/vX.Y.Z`
(nested Go module) tags at the same commit. The module itself lives in `go/` and has path
`github.com/enmaq/mdgl/go`. The old root-module releases `v0.1.0` and `v0.1.1` remain
available; this flow does not delete or replace those tags or their package history.

The nested module at `github.com/enmaq/mdgl/go` is published at `@v0.3.0` (tag `go/v0.3.0`), and the 0.3.0 registry packages are published. The public tags `v0.3.0` and `go/v0.3.0` retain the original source tree, while the registry packages carry corrected version-neutral metadata and README text (see `CHANGELOG.md`); code, API and version are unchanged.

The registry-only cohort uses `scripts/publish-mdgl-packages.sh` and never invokes this
Git-mutating snapshot publisher. Go snapshot publication is a separate release path.

From the monorepo root, run `scripts/publish-mdgl.sh vX.Y.Z` for a dry run. It checks the
committed version and snapshot, requires a matching `## [X.Y.Z]` heading in the root
`CHANGELOG.md`, checks that neither tag already exists, and queries the public `main` ref
without fetching. It compares the snapshot tree when the parent object is already local;
otherwise it reports that comparison as unknown until `--push`. The dry run makes no Git
writes.
Run `bash scripts/test-publish-mdgl.sh` to exercise the dry-run, tag collision, and guarded
push paths with a fake `git` executable and no repository or Git side effects.

`scripts/publish-mdgl.sh --push vX.Y.Z` fetches the public `main`, creates the snapshot commit
and a temporary annotated tag locally, then makes exactly one `git push --atomic` request. That
push targets the snapshot commit at `main` and the temporary tag at both `vX.Y.Z` and
`go/vX.Y.Z`, so all three remote refs move together to the same commit. If the atomic push is
rejected, the script exits nonzero without fallback pushes and removes the temporary local tag.
These are Git mutations: run this mode only after a human has separately authorized the
required commit, branch push, local tag, and remote tag operations. No Go release was attempted
as part of this documentation or publisher change.
