#!/usr/bin/env python3
"""Fail-closed privacy check for MDGL source trees and release archives.

The checker reports only member paths, line numbers, and category names. It never
prints source lines, token values, or hashes of matches.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import stat
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterable

MAX_FILE = 128 * 1024 * 1024
MAX_ARCHIVE = 256 * 1024 * 1024
MAX_MEMBERS = 5000
MEDIA_SUFFIXES = {".gif", ".mp4", ".png", ".jpg", ".jpeg", ".webp"}
DOT = "."
DOT_RE = re.escape(DOT)
VAULT_MARKER = "sensor" + "_pipeline_vars"
FORBIDDEN_NAMES = {
    DOT + "tldrq", DOT + "env", DOT + "env" + DOT + "local",
    DOT + "env" + DOT + "production", DOT + "venv",
    "node_modules", "target", "build", "__pycache__",
}
FORBIDDEN_SUFFIXES = (".keys", ".pem", ".log", ".pprof", ".perf")
SOURCE_BUILD_DIRS = {".venv", "node_modules", "target", "build", "__pycache__"}

TEXT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", re.I)),
    ("credential-assignment", re.compile(
        r"(?i)\b(?:password|passwd|secret|token|api[_-]?key|access[_-]?key)\s*[:=]\s*['\"]?[^\s'\"]{6,}"
    )),
    ("credential-header", re.compile(r"(?i)\b(?:authorization\s*:\s*bearer|x-api-key\s*:)\s*\S+")),
    ("cloud-key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("provider-token", re.compile(r"\b(?:npm_[A-Za-z0-9]{20,}|pypi-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|cio[A-Za-z0-9]{32,})\b")),
    ("home-path", re.compile(r"(?:^|[\s=:'\"])/(?:home|Users|root|work|workspace)/[A-Za-z0-9._-]+")),
    ("private-host", re.compile(r"(?i)\b(?:[a-z0-9-]+\.)+(?:local|internal|lan|corp|intranet)\b")),
    ("loopback-host", re.compile(r"\b" + "local" + "host" + r"\b", re.I)),
    ("private-service-host", re.compile(
        r"(?i)\b(?:" + "voc" + "-reg|" + "eng" + "-voc|" + "bru" + "-[a-z0-9-]+)\b"
    )),
    ("private-ip", re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")),
    ("private-ipv6", re.compile(r"(?<![\w:])(?=[0-9A-Fa-f:]*[0-9A-Fa-f])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")),
    ("leftover-vault", re.compile(r"(?i)(?:" + re.escape(VAULT_MARKER) + r"|enmaq" + DOT_RE + r"keys|(?<![A-Za-z0-9_])" + DOT_RE + r"env(?:\b|/))")),
)


class Finding(Exception):
    def __init__(self, path: str, line: int, category: str):
        self.path, self.line, self.category = path, line, category


class Checker:
    def __init__(self, review_path: Path):
        self.findings: set[tuple[str, int, str]] = set()
        self.review = self._load_review(review_path)
        self.tokens: list[tuple[str, bytes]] = []
        for name in ("NPM_TOKEN", "CARGO_REGISTRY_TOKEN", "PYPI_TOKEN"):
            value = os.environ.get(name, "")
            if value:
                encoded = value.encode("utf-8")
                if len(encoded) < 8:
                    self.report("<environment>", 0, "token-too-short-to-scan")
                else:
                    self.tokens.append((name, encoded))

    @staticmethod
    def _load_review(path: Path) -> dict[str, str]:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            entries = doc["reviewed_media"]
            if not isinstance(entries, dict) or not entries:
                raise ValueError
            result: dict[str, str] = {}
            for name, digest in entries.items():
                p = PurePosixPath(name)
                if p.is_absolute() or ".." in p.parts or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ValueError
                result[str(p)] = digest
            if not doc.get("evidence_sha256") or not doc.get("review_scope"):
                raise ValueError
            return result
        except Exception:
            raise ValueError("invalid media review manifest") from None

    def report(self, path: str, line: int, category: str) -> None:
        self.findings.add((self.safe_label(path), line, category))

    def safe_label(self, raw: str) -> str:
        label = str(raw)
        for _, pattern in TEXT_PATTERNS:
            label = pattern.sub("[redacted]", label)
        for _, value in self.tokens:
            label = label.replace(value.decode("utf-8", "ignore"), "[redacted]")
        encoded = label.encode("utf-8", "replace")
        label = "".join(chr(byte) if 0x20 <= byte <= 0x7E else f"%{byte:02X}" for byte in encoded)
        return label[:240] + ("…" if len(label) > 240 else "")

    def check_member_name(self, path: str) -> None:
        if any(pattern.search(path) for _, pattern in TEXT_PATTERNS) or any(
            value.decode("utf-8", "ignore") in path for _, value in self.tokens
        ):
            self.report(path, 0, "sensitive-filename")

    @staticmethod
    def _safe_rel(raw: str) -> str | None:
        if "\x00" in raw or "\\" in raw or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw):
            return None
        p = PurePosixPath(raw)
        if p.is_absolute() or any(part in ("", ".", "..") for part in p.parts):
            return None
        if p.parts and re.match(r"^[A-Za-z]:", p.parts[0]):
            return None
        return str(p)

    @staticmethod
    def _forbidden(path: str) -> str | None:
        for part in PurePosixPath(path).parts:
            if part in FORBIDDEN_NAMES:
                return "forbidden-leftover"
            if any(part.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
                return "forbidden-leftover"
        return None

    def _media_key(self, path: str) -> str:
        parts = PurePosixPath(path).parts
        # Archives commonly add one package root; source paths may start at v/mdgl.
        for i in range(len(parts)):
            suffix = "/".join(parts[i:])
            if suffix in self.review:
                return suffix
        return path

    def scan_content(self, path: str, data: bytes, *, allow_media: bool = True) -> None:
        if len(data) > MAX_FILE:
            self.report(path, 0, "file-too-large")
            return
        if any(value in data for _, value in self.tokens):
            self.report(path, 0, "registry-token")
        suffix = PurePosixPath(path).suffix.lower()
        if suffix in MEDIA_SUFFIXES:
            if not allow_media:
                self.report(path, 0, "media-review-required")
                return
            digest = __import__("hashlib").sha256(data).hexdigest()
            key = self._media_key(path)
            if self.review.get(key) != digest:
                self.report(path, 0, "media-review-required")
            return
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            self.report(path, 0, "unsupported-binary")
            return
        for number, line in enumerate(text.splitlines(), 1):
            # Narrow allowance: public loopback test fixtures in conformance/examples only.
            path_parts = PurePosixPath(path).parts
            loopback_v6 = ":" * 2 + "1"
            loopback_fixture = (("127.0.0." + "1") in line or loopback_v6 in line or ("local" + "host") in line) and (
                "conformance" in path_parts or "examples" in path_parts
            )
            for category, pattern in TEXT_PATTERNS:
                for match in pattern.finditer(line):
                    if loopback_fixture and category == "private-ip" and match.group(0) == "127.0.0." + "1":
                        continue
                    if loopback_fixture and category == "loopback-host" and match.group(0).lower() == "local" + "host":
                        continue
                    value = match.group(0)
                    if category == "private-ip":
                        try:
                            addr = ipaddress.ip_address(value)
                        except ValueError:
                            continue
                        if addr.is_loopback and loopback_fixture:
                            continue
                        if not (addr.is_private or addr.is_link_local or addr.is_reserved):
                            continue
                    if category == "private-ipv6":
                        try:
                            addr = ipaddress.ip_address(value)
                        except ValueError:
                            continue
                        if addr.is_loopback and loopback_fixture:
                            continue
                        if not (addr.is_private or addr.is_link_local or addr.is_reserved):
                            continue
                    self.report(path, number, category)

    def scan_tree(self, root: Path, label: str) -> None:
        if not root.is_dir() or root.is_symlink():
            self.report(label, 0, "unsafe-source-root")
            return
        for base, dirs, files in os.walk(root, followlinks=False):
            dirs.sort()
            files.sort()
            relbase = Path(base).relative_to(root).as_posix()
            kept: list[str] = []
            for name in dirs:
                rel = name if relbase == "." else f"{relbase}/{name}"
                full = Path(base) / name
                # Build tools write these only into the staged workspace after staging;
                # package archives are scanned separately and still reject these paths.
                if name in SOURCE_BUILD_DIRS or name.endswith(".egg-info"):
                    continue
                category = self._forbidden(rel)
                if category:
                    self.report(f"{label}/{rel}", 0, category)
                    continue
                if full.is_symlink():
                    self.report(f"{label}/{rel}", 0, "unsafe-symlink")
                    continue
                kept.append(name)
            dirs[:] = kept
            for name in files:
                rel = name if relbase == "." else f"{relbase}/{name}"
                full = Path(base) / name
                safe = self._safe_rel(rel)
                if safe is None or full.is_symlink() or not full.is_file():
                    self.report(f"{label}/{rel}", 0, "unsafe-filesystem-entry")
                    continue
                self.check_member_name(safe)
                category = self._forbidden(safe)
                if category:
                    self.report(f"{label}/{safe}", 0, category)
                    continue
                try:
                    size = full.stat().st_size
                    if size > MAX_FILE:
                        self.report(f"{label}/{safe}", 0, "file-too-large")
                        continue
                    self.scan_content(f"{label}/{safe}", full.read_bytes())
                except OSError:
                    self.report(f"{label}/{safe}", 0, "source-read-error")

    def _scan_member(self, path: str, stream: BinaryIO, size: int, total: list[int]) -> None:
        safe = self._safe_rel(path)
        if safe is None:
            self.report(path or "<archive>", 0, "unsafe-archive-path")
            return
        self.check_member_name(safe)
        category = self._forbidden(safe)
        if category:
            self.report(safe, 0, category)
            return
        if size < 0 or size > MAX_FILE or total[0] + size > MAX_ARCHIVE:
            self.report(safe, 0, "archive-size-limit")
            return
        data = stream.read(size + 1)
        if len(data) != size:
            self.report(safe, 0, "archive-member-size-mismatch")
            return
        total[0] += size
        self.scan_content(safe, data)

    def scan_archive(self, archive: str) -> None:
        total = [0]
        try:
            if archive == "-":
                tf_context = tarfile.open(fileobj=sys.stdin.buffer, mode="r|*")
            else:
                path = Path(archive)
                if not path.is_file() or path.stat().st_size > MAX_ARCHIVE:
                    self.report(archive, 0, "archive-size-limit")
                    return
                if zipfile.is_zipfile(path):
                    with zipfile.ZipFile(path) as zf:
                        infos = zf.infolist()
                        if len(infos) > MAX_MEMBERS:
                            self.report(archive, 0, "archive-member-limit")
                            return
                        seen: set[str] = set()
                        for info in infos:
                            safe = self._safe_rel(info.filename.rstrip("/"))
                            mode = (info.external_attr >> 16) & 0xFFFF
                            if safe is None or safe in seen:
                                self.report(info.filename, 0, "unsafe-archive-path")
                                continue
                            seen.add(safe)
                            self.check_member_name(safe)
                            file_type = stat.S_IFMT(mode)
                            if stat.S_ISLNK(mode) or (file_type not in (0, stat.S_IFREG)):
                                self.report(safe, 0, "unsafe-archive-member")
                                continue
                            if info.is_dir():
                                category = self._forbidden(safe)
                                if category:
                                    self.report(safe, 0, category)
                                continue
                            if info.flag_bits & 1:
                                self.report(safe, 0, "encrypted-archive-member")
                                continue
                            if info.file_size > MAX_FILE or total[0] + info.file_size > MAX_ARCHIVE:
                                self.report(safe, 0, "archive-size-limit")
                                continue
                            with zf.open(info) as stream:
                                self._scan_member(safe, stream, info.file_size, total)
                    return
                tf_context = tarfile.open(path, mode="r|*")
            with tf_context as tf:
                count = 0
                seen: set[str] = set()
                for member in tf:
                    count += 1
                    if count > MAX_MEMBERS:
                        self.report(archive if archive != "-" else "<stdin>", 0, "archive-member-limit")
                        break
                    safe = self._safe_rel(member.name.rstrip("/"))
                    if safe is None or safe in seen:
                        self.report(member.name, 0, "unsafe-archive-path")
                        continue
                    seen.add(safe)
                    self.check_member_name(safe)
                    if member.isdir():
                        category = self._forbidden(safe)
                        if category:
                            self.report(safe, 0, category)
                    elif not member.isfile():
                        self.report(safe, 0, "unsafe-archive-member")
                    elif member.size < 0 or member.size > MAX_FILE or total[0] + member.size > MAX_ARCHIVE:
                        self.report(safe, 0, "archive-size-limit")
                        break
                    else:
                        stream = tf.extractfile(member)
                        if stream is None:
                            self.report(safe, 0, "archive-read-error")
                        else:
                            self._scan_member(safe, stream, member.size, total)
        except (OSError, tarfile.TarError, zipfile.BadZipFile, EOFError, ValueError):
            self.report(archive if archive != "-" else "<stdin>", 0, "archive-read-error")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", default=[], metavar="DIR")
    parser.add_argument("--archive", action="append", default=[], metavar="FILE|-" )
    parser.add_argument("--media-review", required=True, metavar="JSON")
    args = parser.parse_args(argv)
    try:
        checker = Checker(Path(args.media_review))
    except ValueError as exc:
        print(f"privacy gate: FAIL <manifest>:0 {exc}", file=sys.stderr)
        return 2
    for source in args.source:
        checker.scan_tree(Path(source), Path(source).name or "source")
    for archive in args.archive:
        checker.scan_archive(archive)
    if checker.findings:
        for path, line, category in sorted(checker.findings):
            print(f"privacy gate: FAIL {path}:{line} {category}", file=sys.stderr)
        return 1
    print("privacy gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
