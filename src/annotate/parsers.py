from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
import re
from typing import Any

from constants import (
    AREA_AGGREGATION,
    CANTON_PATTERNS,
    COMMON_AREA_KEYWORDS,
    DOI_VERSION,
    FEDERAL_SOURCE_PATTERNS,
    MONTHS,
    PROC_TYPE_BY_LETTER,
)


CASE_RE = re.compile(r"\b([1-9][A-Z][_.]\d+/\d{4})\b")
BGE_RE = re.compile(r"\b(?:BGE|ATF|DTF)\s+\d{3,4}\s+[IVX]+\s+\d+\b")
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{2,4})\b")
TEXT_DATE_RE = re.compile(
    r"\b(\d{1,2})(?:er|\.)?\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})\b",
    re.IGNORECASE,
)


def normalize_space(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def lower(value: str) -> str:
    return normalize_space(value).casefold()


def first_match(pattern: re.Pattern[str], values: Sequence[str]) -> str | None:
    for value in values:
        match = pattern.search(value)
        if match:
            return match.group(1)
    return None


def docref_from_docid(docid: str | None) -> str | None:
    if not docid:
        return None
    match = re.search(r"([1-9][A-Z][_.]\d+)-(\d{4})$", docid)
    if not match:
        return None
    case_number, year = match.groups()
    return f"{case_number.replace('.', '_')}/{year}"


def extract_docref(paragraphs: Sequence[str], registry_record: Mapping[str, Any] | None) -> str | None:
    if registry_record is not None:
        docid = registry_record.get("docid")
        registry_docref = docref_from_docid(docid if isinstance(docid, str) else None)
        if registry_docref is not None:
            return registry_docref

    docref = first_match(CASE_RE, paragraphs[:12])
    if docref is not None:
        return docref.replace(".", "_")
    return None


def parse_date_text(value: str) -> date | None:
    numeric = NUMERIC_DATE_RE.search(value)
    if numeric:
        day, month, year = numeric.groups()
        year_int = int(year)
        if year_int < 100:
            year_int += 2000 if year_int < 50 else 1900
        try:
            return date(year_int, int(month), int(day))
        except ValueError:
            return None

    textual = TEXT_DATE_RE.search(value)
    if textual:
        day, month_name, year = textual.groups()
        month = MONTHS.get(month_name.casefold())
        if month is None:
            return None
        try:
            return date(int(year), month, int(day))
        except ValueError:
            return None

    return None


def find_dates(value: str) -> list[date]:
    dates: list[date] = []
    for match in NUMERIC_DATE_RE.finditer(value):
        parsed = parse_date_text(match.group(0))
        if parsed is not None:
            dates.append(parsed)
    for match in TEXT_DATE_RE.finditer(value):
        parsed = parse_date_text(match.group(0))
        if parsed is not None:
            dates.append(parsed)
    return dates


def extract_judgment_date(
    paragraphs: Sequence[str],
    registry_record: Mapping[str, Any] | None,
) -> str | None:
    for paragraph in paragraphs[:12]:
        lowered = lower(paragraph)
        if any(marker in lowered for marker in ("urteil vom", "arrêt du", "sentenza del")):
            parsed = parse_date_text(paragraph)
            if parsed is not None:
                return parsed.isoformat()

    if registry_record is not None:
        registry_date = registry_record.get("decision_date")
        if isinstance(registry_date, str) and registry_date:
            return registry_date
    return None


def detect_language(paragraphs: Sequence[str], registry_record: Mapping[str, Any] | None) -> str | None:
    head = "\n".join(paragraphs[:20]).casefold()
    if "arrêt du" in head or "objet" in head or "parties" in head:
        return "fr"
    if "sentenza del" in head or "oggetto" in head or "parti" in head:
        return "it"
    if "urteil vom" in head or "gegenstand" in head or "parteien" in head:
        return "de"
    if registry_record is None:
        return None
    language = registry_record.get("language")
    return language if isinstance(language, str) else None


def proc_type_from_docref(docref: str | None) -> str | None:
    if not docref:
        return None
    match = re.match(r"^\d+([A-Z])", docref)
    if match is None:
        return None
    return PROC_TYPE_BY_LETTER.get(match.group(1))


def division_from_docref(docref: str | None, judgment_date: str | None) -> str | None:
    if not docref:
        return None
    digit = docref[0]
    cutoff_social = judgment_date is not None and judgment_date >= "2023-01-01"
    cutoff_criminal = judgment_date is not None and judgment_date >= "2023-07-01"

    if digit == "1":
        return "1. Public"
    if digit == "2":
        return "2. Public"
    if digit == "4":
        return "1. Civil"
    if digit == "5":
        return "2. Civil"
    if digit == "6":
        return "1. Criminal" if cutoff_criminal else "Criminal"
    if digit == "7":
        return "2. Criminal" if cutoff_criminal else "Criminal"
    if digit == "8":
        return "4. Public" if cutoff_social else "1. Social"
    if digit == "9":
        return "3. Public" if cutoff_social else "2. Social"
    return None


def division_type_from_division(division: str | None) -> str | None:
    if division is None:
        return None
    if "Civil" in division:
        return "Civil"
    if "Criminal" in division:
        return "Criminal"
    if "Public" in division or "Social" in division:
        return "Public"
    return None


def find_marker_index(paragraphs: Sequence[str], markers: Sequence[str]) -> int | None:
    lowered_markers = tuple(marker.casefold() for marker in markers)
    for index, paragraph in enumerate(paragraphs):
        marker = re.sub(r"^\d+\.\s*", "", lower(paragraph).strip(" :"))
        if marker in lowered_markers:
            return index
    return None


def composition_block(paragraphs: Sequence[str]) -> list[str]:
    start = find_marker_index(paragraphs, ("Besetzung", "Composition", "Composizione"))
    if start is None:
        return []

    stop_markers = {
        "parteien",
        "parties",
        "parti",
        "beteiligte",
        "participants",
        "participants à la procédure",
        "oggetto",
        "objet",
        "gegenstand",
    }
    block: list[str] = []
    for paragraph in paragraphs[start + 1 : start + 12]:
        marker = re.sub(r"^\d+\.\s*", "", lower(paragraph).strip(" :"))
        if marker in stop_markers or any(marker.startswith(f"{stop} ") for stop in stop_markers):
            break
        block.append(paragraph)
    return block


def extract_judges(paragraphs: Sequence[str]) -> tuple[int | None, list[str]]:
    block = composition_block(paragraphs)
    if not block:
        return None, []

    text = " ".join(block)
    text = re.sub(
        r"(Gerichtsschreiber(?:in)?|Greffi(?:er|ère)|cancellier[aeo]?|cancelliera).*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?:\b(?:Bundesrichter(?:in|innen)?|Juge(?:s)? fédér(?:al|aux|ale|ales)|Juges?|Giudic[ei] federal[ei]|Mme|Mmes|M)\b\.?|\bMM\.)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(président de la Cour|presidente della Corte|präsidierendes Mitglied|membre présidant|Präsident(?:in)?|président(?:e)?|presidente)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(giudice supplente|juge suppléant|juge suppléante|suppléant|suppléante|supplente)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = text.replace(" und ", ",").replace(" et ", ",").replace(" e ", ",")
    candidates = [
        normalize_space(part.strip(" .:;"))
        for part in text.split(",")
        if normalize_space(part.strip(" .:;"))
    ]
    candidates = [re.sub(r"^(?:les|le|la|gli|i)\s+", "", candidate, flags=re.IGNORECASE) for candidate in candidates]
    names = [
        candidate
        for candidate in candidates
        if not re.search(r"gerichtsschreiber|greffi|cancell", candidate, re.IGNORECASE)
    ]
    return (len(names) if names else None), names


def extract_issue_and_topic(paragraphs: Sequence[str]) -> tuple[str | None, str | None]:
    start = find_marker_index(paragraphs, ("Gegenstand", "Objet", "Oggetto"))
    if start is None:
        return None, None

    stop_terms = (
        "sachverhalt",
        "faits",
        "fatti",
        "erwägung",
        "considérant",
        "considerando",
        "das bundesgericht zieht",
        "le tribunal fédéral considère",
        "le président de la",
        "la présidente de la",
        "il presidente della",
        "la presidente della",
        "nach einsicht",
        "in erwägung",
        "vu:",
        "vu ",
        "visto",
        "considerando",
        "diritto",
    )
    lines: list[str] = []
    for paragraph in paragraphs[start + 1 : start + 8]:
        lowered = lower(paragraph)
        if any(lowered.startswith(term) for term in stop_terms):
            break
        if re.fullmatch(r"[A-Z]\.|[0-9]+\.?", paragraph.strip()):
            break
        lines.append(paragraph)

    if not lines:
        return None, None
    issue = normalize_space(" ".join(lines))
    topic = normalize_space(lines[0].rstrip(",.;"))
    return topic or None, issue or None


def extract_source_date(issue: str | None) -> str | None:
    if not issue:
        return None
    context = re.split(
        r"\b(?:nach einsicht|in erwägung|vu\s*:|visto|considerando)\b",
        issue,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    dates = find_dates(context)
    return max(dates).isoformat() if dates else None


def extract_source_canton(issue: str | None) -> str | None:
    if not issue:
        return None
    text = lower(issue)
    if any(pattern in text for pattern in FEDERAL_SOURCE_PATTERNS):
        return "CH"
    for canton, patterns in CANTON_PATTERNS.items():
        if any(pattern in text for pattern in patterns):
            return canton
    return None


def days_between(end_date: str | None, start_date: str | None) -> int | None:
    if not end_date or not start_date:
        return None
    try:
        end = date.fromisoformat(end_date)
        start = date.fromisoformat(start_date)
    except ValueError:
        return None
    return (end - start).days


def extract_merged_cases(
    docref: str | None,
    text: str,
    paragraphs: Sequence[str] | None = None,
) -> bool:
    if paragraphs is not None:
        text = " ".join(paragraphs[:8])
    matches = CASE_RE.findall(text)
    normalized = {match.replace(".", "_") for match in matches}
    if docref:
        normalized.discard(docref.replace(".", "_"))
    return bool(normalized)


def extract_party_block(paragraphs: Sequence[str]) -> tuple[str | None, str | None, str | None]:
    start = find_marker_index(
        paragraphs,
        (
            "Parteien",
            "Parties",
            "Parti",
            "Verfahrensbeteiligte",
            "Participants",
            "Participants à la procédure",
        ),
    )
    if start is None:
        return None, None, None
    end = find_marker_index(paragraphs[start + 1 :], ("Gegenstand", "Objet", "Oggetto"))
    stop = start + 1 + end if end is not None else min(len(paragraphs), start + 16)
    block = normalize_space(" ".join(paragraphs[start + 1 : stop]))
    parts = re.split(r"\b(?:gegen|contre|contro)\b", block, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        return block, normalize_space(parts[0]), normalize_space(parts[1])
    return block, None, None


def classify_party(value: str | None) -> str | None:
    if not value:
        return None
    text = lower(value)
    state_terms = (
        "kanton",
        "gemeinde",
        "regierungsrat",
        "verwaltungsgericht",
        "staatsanwaltschaft",
        "bundesanwaltschaft",
        "bundeskriminalpolizei",
        "departement",
        "amt",
        "office",
        "tribunal",
        "conseil d'etat",
        "conseil d'état",
        "consiglio di stato",
        "ministère public",
        "procureur général",
        "procureure générale",
        "police",
        "service de",
    )
    legal_terms = (
        "stiftung",
        "association",
        "verein",
        "inc.",
        "ltd",
        "versicherung",
        "assurance",
        "bank",
    )
    if any(term in text for term in state_terms):
        return "state"
    if re.search(r"(?:\b|_+)(?:ag|gmbh|sa|sàrl|sarl|llc|ltd|inc)\b", text):
        return "legal"
    if any(term in text for term in legal_terms):
        return "legal"
    return "natural"


def is_represented(value: str | None) -> bool | None:
    if not value:
        return None
    text = lower(value)
    lawyer_terms = (
        "rechtsanwalt",
        "rechtsanwältin",
        "anwalt",
        "avocat",
        "avocate",
        "avvocato",
        "avvocatessa",
        " me ",
    )
    return any(term in f" {text} " for term in lawyer_terms)


def holdings_text(paragraphs: Sequence[str]) -> str:
    markers = (
        "demnach erkennt",
        "par ces motifs",
        "per questi motivi",
        "erkennt das bundesgericht",
    )
    for index, paragraph in enumerate(paragraphs):
        if any(marker in lower(paragraph) for marker in markers):
            return normalize_space(" ".join(paragraphs[index:]))
    return normalize_space(" ".join(paragraphs[-18:]))


def extract_outcome(paragraphs: Sequence[str]) -> str | None:
    text = lower(holdings_text(paragraphs))
    if any(
        term in text
        for term in (
            "teilweise gutheissung",
            "teilweise gutgeheissen",
            "partiellement admis",
            "parzialmente accolto",
        )
    ):
        return "partly granted"
    if any(
        term in text
        for term in (
            "nicht eingetreten",
            "nicht einzutreten",
            "n'entre pas en matière",
            "irrecevable",
            "inammissible",
            "inammissibile",
            "non entra nel merito",
        )
    ):
        return "inadmissible"
    if any(term in text for term in ("wird gutgeheissen", "recours est admis", "ricorso è accolto")):
        return "granted"
    if any(term in text for term in ("wird abgewiesen", "recours est rejeté", "ricorso è respinto")):
        return "rejected"
    if any(
        term in text
        for term in (
            "verfahren wird abgeschrieben",
            "als gegenstandslos abgeschrieben",
            "cause est rayée du rôle",
            "rayé du rôle",
            "stralciata",
            "stralciato",
        )
    ):
        return "writeoff"
    return None


def outcome_binary(outcome: str | None) -> bool | None:
    if outcome in {"granted", "partly granted"}:
        return True
    if outcome in {"inadmissible", "rejected"}:
        return False
    return None


def extract_citations(text: str, docref: str | None) -> tuple[str | None, int, str | None, int]:
    bger = CASE_RE.findall(text)
    if docref and docref not in bger and docref.replace("_", ".") not in text:
        bger.insert(0, docref)

    bge = [
        re.sub(r"^(?:BGE|ATF|DTF)\s+", "", normalize_space(match.group(0)))
        for match in BGE_RE.finditer(text)
    ]
    return (
        ";".join(bger) if bger else None,
        len(bger),
        ";".join(bge) if bge else None,
        len(bge),
    )


def extract_leading_case(paragraphs: Sequence[str]) -> str | None:
    head = " ".join(paragraphs[:15])
    match = re.search(r"\bBGE\s+(\d{3,4}\s+[IVX]+\s+\d+)\b", head)
    return match.group(1) if match else None


def classify_area(topic: str | None, issue: str | None, text: str) -> tuple[str | None, str | None, str | None]:
    haystack = lower(" ".join(value for value in (topic, issue, text[:3000]) if value))
    for detailed, keywords in COMMON_AREA_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            intermediate, general = AREA_AGGREGATION[detailed]
            return detailed, intermediate, general
    return None, None, None


def build_base_annotation(
    extracted_record: Mapping[str, Any],
    registry_record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    paragraphs = extracted_record.get("paragraphs")
    if not isinstance(paragraphs, list):
        paragraphs = []
    paragraphs = [str(paragraph) for paragraph in paragraphs]
    text = str(extracted_record.get("text") or "\n".join(paragraphs))

    docref = extract_docref(paragraphs, registry_record)
    judgment_date = extract_judgment_date(paragraphs, registry_record)
    division = division_from_docref(docref, judgment_date)
    n_judges, judge_names = extract_judges(paragraphs)
    topic, issue = extract_issue_and_topic(paragraphs)
    source_date = extract_source_date(issue)
    party_block, appellant, respondent = extract_party_block(paragraphs)
    area_detailed, area_intermediate, area_general = classify_area(topic, issue, text)
    outcome = extract_outcome(paragraphs)
    cited_bger, n_cited_bger, cited_bge, n_cited_bge = extract_citations(text, docref)

    url = registry_record.get("url") if registry_record is not None else None
    raw_html_path = extracted_record.get("raw_html_path")

    evidence = {}
    if issue:
        evidence["issue"] = issue
    if party_block:
        evidence["parties"] = party_block
    if outcome:
        evidence["outcome"] = holdings_text(paragraphs)[:1000]

    warnings = []
    for field, value in (
        ("docref", docref),
        ("date", judgment_date),
        ("n_judges", n_judges),
        ("issue", issue),
        ("source_date", source_date),
        ("outcome", outcome),
    ):
        if value is None:
            warnings.append(f"missing_{field}")

    return {
        "docref": docref,
        "url": url if isinstance(url, str) else None,
        "date": judgment_date,
        "year": int(judgment_date[:4]) if judgment_date else None,
        "proc_type": proc_type_from_docref(docref),
        "merged_cases": extract_merged_cases(docref, text, paragraphs),
        "division": division,
        "division_type": division_type_from_division(division),
        "n_judges": n_judges,
        "language": detect_language(paragraphs, registry_record),
        "length": len(text),
        "area_general": area_general,
        "area_intermediate": area_intermediate,
        "area_detailed": area_detailed,
        "topic": topic,
        "issue": issue,
        "source_date": source_date,
        "source_canton": extract_source_canton(issue),
        "proc_duration": days_between(judgment_date, source_date),
        "app_class": classify_party(appellant),
        "app_represented": is_represented(appellant),
        "resp_class": classify_party(respondent),
        "resp_represented": is_represented(respondent),
        "outcome": outcome,
        "outcome_binary": outcome_binary(outcome),
        "cited_bger": cited_bger,
        "n_cited_bger": n_cited_bger,
        "cited_bge": cited_bge,
        "n_cited_bge": n_cited_bge,
        "leading_case": extract_leading_case(paragraphs),
        "doi_version": DOI_VERSION,
        "html_id": str(extracted_record.get("html_id") or ""),
        "raw_html_path": str(raw_html_path or ""),
        "evidence": evidence,
        "warnings": warnings,
        "judge_names": judge_names,
        "_llm_context": {
            "topic": topic,
            "issue": issue,
            "parties": party_block,
            "holdings": holdings_text(paragraphs)[:1600],
            "text_start": text[:3000],
        },
    }
