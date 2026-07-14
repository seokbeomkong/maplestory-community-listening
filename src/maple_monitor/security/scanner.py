from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass
from typing import Final


_EVIDENCE_LIMIT: Final = 160
_CONTROL_CATEGORIES: Final = frozenset({"Cc", "Cf"})
_SOURCE_KIND_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


@dataclass(frozen=True)
class Finding:
    rule_id: str
    score: int
    evidence_hash: str
    escaped_evidence: str


@dataclass(frozen=True)
class ScanResult:
    normalized_text: str
    findings: tuple[Finding, ...]

    @property
    def risk_score(self) -> int:
        return min(100, sum(item.score for item in self.findings))

    def quarantined(self, threshold: int) -> bool:
        if isinstance(threshold, bool) or not isinstance(threshold, int):
            raise TypeError("threshold must be an integer")
        if not 1 <= threshold <= 100:
            raise ValueError("threshold must be between 1 and 100")
        return self.risk_score >= threshold


_INSTRUCTION_OVERRIDE = re.compile(
    r"(?:\b(?:ignore|disregard|forget|override)\b[^,.;:!?-]{0,50}?"
    r"\b(?:previous|prior|above|earlier|system)\b[^,.;:!?-]{0,30}?"
    r"\b(?:instructions?|prompts?|commands?)\b)"
    r"|(?:(?<!\w)(?:앞선|이전|위의|기존)(?!\w)[^,.;:!?-]{0,30}?"
    r"(?<!\w)(?:명령|지시|프롬프트)(?:을|를)?(?!\w)[^,.;:!?-]{0,20}?"
    r"(?<!\w)(?:무시(?!무시)|따르지|재정의|덮어쓰))",
    re.IGNORECASE,
)

_SECRET_OR_ENVIRONMENT_REQUEST = re.compile(
    r"(?:\b(?:print|show|read|reveal|expose|modify|change|edit|set|dump)\b"
    r"[\s\S]{0,60}?(?:\.env\b|\bapi[\s_-]*key\b|\benvironment\s+variables?\b|"
    r"\bsecrets?\b|\baccess[\s_-]*tokens?\b|\bpasswords?\b))"
    r"|(?:(?:\.env\b|\bapi[\s_-]*key\b|\benvironment\s+variables?\b|"
    r"\bsecrets?\b|\baccess[\s_-]*tokens?\b|\bpasswords?\b)"
    r"[\s\S]{0,60}?\b(?:print|show|read|reveal|expose|modify|change|edit|set|dump)\b)"
    r"|(?:(?:출력|보여|읽|공개|수정|변경|설정|접근|내놔)"
    r"[\s\S]{0,40}?(?:환경\s*변수|비밀|API[\s_-]*키|접근\s*토큰|비밀번호))"
    r"|(?:(?:환경\s*변수|비밀|API[\s_-]*키|접근\s*토큰|비밀번호)"
    r"[\s\S]{0,40}?(?:출력|보여|읽|공개|수정|변경|설정|접근|내놔))",
    re.IGNORECASE,
)

_TOOL_OR_SHELL_REQUEST = re.compile(
    r"(?:\b(?:run|execute|launch|invoke|open|use)\b[\s\S]{0,60}?"
    r"\b(?:shell|bash|powershell|cmd|terminal|command)\b)"
    r"|(?:\b(?:shell|bash|powershell|cmd|terminal|command)\b[\s\S]{0,60}?"
    r"\b(?:run|execute|launch|invoke|open|use)\b)"
    r"|(?:(?:셸|쉘|터미널|명령어|파워셸|파워쉘|bash|powershell|cmd)"
    r"[\s\S]{0,40}?(?:실행|열어|사용|호출))"
    r"|(?:(?:실행|열어|사용|호출)[\s\S]{0,40}?"
    r"(?:셸|쉘|터미널|명령어|파워셸|파워쉘|bash|powershell|cmd))",
    re.IGNORECASE,
)

_SYSTEM_IMPERSONATION = re.compile(
    r"(?:<\s*(?:/\s*)?system(?:\s|>)|\[\s*system\s*\]|\bsystem\s+(?:prompt|message|role)\b|"
    r"\byou\s+are\s+now\s+(?:the\s+)?(?:system|developer)\b|"
    r"<\s*(?:/\s*)?시스템(?:\s|>)|\[\s*시스템\s*\]|시스템\s*(?:프롬프트|메시지|역할))",
    re.IGNORECASE,
)

_RULES: Final = (
    ("prompt.instruction-override", 70, _INSTRUCTION_OVERRIDE),
    ("prompt.secret-or-environment-request", 70, _SECRET_OR_ENVIRONMENT_REQUEST),
    ("prompt.tool-or-shell-request", 60, _TOOL_OR_SHELL_REQUEST),
    ("prompt.system-impersonation", 60, _SYSTEM_IMPERSONATION),
)


def _validate_source_kind(source_kind: str) -> None:
    if not isinstance(source_kind, str):
        raise TypeError("source_kind must be a string")
    if _SOURCE_KIND_PATTERN.fullmatch(source_kind) is None:
        raise ValueError(
            "source_kind must be a 1-64 character lowercase identifier "
            "containing only letters, digits, and underscores"
        )


def _control_escape(character: str) -> str:
    code_point = ord(character)
    if code_point <= 0xFFFF:
        return f"\\u{code_point:04x}"
    return f"\\U{code_point:08x}"


def _evidence(value: str) -> tuple[str, str]:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    clipped = value[:_EVIDENCE_LIMIT]
    control_safe = "".join(
        _control_escape(character)
        if unicodedata.category(character) in _CONTROL_CATEGORIES
        else character
        for character in clipped
    )
    return digest, html.escape(control_safe, quote=True)


def _detection_variants(normalized_text: str) -> tuple[str, ...]:
    separated_characters: list[str] = []
    collapsed_characters: list[str] = []
    for character in normalized_text:
        category = unicodedata.category(character)
        if category == "Cf":
            separated_characters.append(" ")
            continue
        if category == "Cc":
            separated_characters.append(" ")
        else:
            separated_characters.append(character)
            collapsed_characters.append(character)

    separated_text = "".join(separated_characters)
    collapsed_text = "".join(collapsed_characters)
    if collapsed_text == separated_text:
        return (separated_text,)
    return separated_text, collapsed_text


def scan_untrusted(text: str, source_kind: str) -> ScanResult:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    _validate_source_kind(source_kind)

    normalized_text = unicodedata.normalize("NFKC", text)
    findings: list[Finding] = []
    invisible = "".join(
        character
        for character in normalized_text
        if unicodedata.category(character) in _CONTROL_CATEGORIES and character not in "\n\t\r"
    )
    if invisible:
        evidence_hash, escaped_evidence = _evidence(invisible)
        findings.append(
            Finding(
                rule_id="text.invisible-control",
                score=30,
                evidence_hash=evidence_hash,
                escaped_evidence=escaped_evidence,
            )
        )

    searchable_texts = _detection_variants(normalized_text)
    for rule_id, score, pattern in _RULES:
        match = next(
            (
                candidate
                for searchable_text in searchable_texts
                if (candidate := pattern.search(searchable_text)) is not None
            ),
            None,
        )
        if match is None:
            continue
        evidence_hash, escaped_evidence = _evidence(match.group(0))
        findings.append(
            Finding(
                rule_id=rule_id,
                score=score,
                evidence_hash=evidence_hash,
                escaped_evidence=escaped_evidence,
            )
        )

    return ScanResult(normalized_text=normalized_text, findings=tuple(findings))
