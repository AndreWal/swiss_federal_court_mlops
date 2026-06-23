from __future__ import annotations

from pathlib import Path
import sys
from typing import Any


ANNOTATE_DIR = Path(__file__).resolve().parents[1] / "src" / "annotate"
sys.path.insert(0, str(ANNOTATE_DIR))

from constants import DOI_VERSION  # noqa: E402
from models import LlmClassification  # noqa: E402
from ollama_client import apply_llm_classification, mock_classification_json  # noqa: E402
from parsers import (  # noqa: E402
    build_base_annotation,
    classify_party,
    days_between,
    division_from_docref,
    division_type_from_division,
    extract_citations,
    extract_docref,
    extract_merged_cases,
    extract_judges,
    extract_outcome,
    extract_party_block,
    extract_source_canton,
    extract_source_date,
    outcome_binary,
    proc_type_from_docref,
)


GERMAN_PARAGRAPHS = [
    "Tribunale federale",
    "Tribunal federal",
    "9C_161/2007",
    "Urteil vom 6. September 2007",
    "II. sozialrechtliche Abteilung",
    "Besetzung",
    "Bundesrichter Lustenberger, präsidierendes Mitglied,",
    "Bundesrichter Borella, Seiler,",
    "Gerichtsschreiber R. Widmer.",
    "Parteien",
    "B.________, Beschwerdeführerin,",
    "gegen",
    "Kanton Zürich, vertreten durch Rechtsanwältin Nina Tinner, Beschwerdegegner.",
    "Gegenstand",
    "Berufliche Vorsorge,",
    "Beschwerde gegen den Entscheid des Sozialversicherungsgerichts des Kantons Zürich vom 15. März 2007.",
    "Sachverhalt:",
    "A.",
    "Demnach erkennt das Bundesgericht:",
    "1.",
    "Die Beschwerde wird abgewiesen.",
]


FRENCH_PARAGRAPHS = [
    "Tribunal fédéral",
    "5A_643/2017",
    "Arrêt du 3 mai 2018",
    "IIe Cour de droit civil",
    "Composition",
    "MM. et Mme les Juges fédéraux von Werdt, Président, Escher et Herrmann.",
    "Greffière : Mme Dolivo.",
    "Parties",
    "A., représenté par Me F., avocat, recourante,",
    "contre",
    "Office des poursuites du district de Lausanne, intimée.",
    "Objet",
    "validité de la poursuite (représentation de l'hoirie en cas d'urgence),",
    "recours contre l'arrêt de la Cour des poursuites et faillites du Tribunal cantonal du canton de Vaud du 16 août 2017.",
    "Par ces motifs, le Tribunal fédéral prononce:",
    "1.",
    "Le recours est admis.",
]


FRENCH_SINGLE_JUDGE_PARAGRAPHS = [
    "Tribunal fédéral",
    "4D_46/2008",
    "Arrêt du 6 juin 2008",
    "Président de la Ire Cour de droit civil",
    "Composition",
    "M. le Juge Corboz, président de la Cour.",
    "Greffier: M. Carruzzo.",
    "Parties",
    "X.________,",
    "recourant,",
    "contre",
    "Y.________SA,",
    "intimée.",
    "Objet",
    "assistance judiciaire gratuite,",
    "recours constitutionnel contre l'arrêt rendu le 1er avril 2008 par la Cour civile du Tribunal cantonal du canton du Jura.",
    "Le Président de la Ire Cour de droit civil,",
    "Vu l'arrêt du 1er avril 2008 par lequel la Cour civile du Tribunal cantonal du canton du Jura a rejeté le recours.",
]


ITALIAN_PARAGRAPHS = [
    "Tribunale federale",
    "2A.628/2006",
    "Sentenza del 27 marzo 2007",
    "II Corte di diritto pubblico",
    "Composizione",
    "Giudici federali Merkli, presidente,",
    "Wurzburger, Müller,",
    "cancelliera Ieronimo Perroud.",
    "Parti",
    "A.________, ricorrente, patrocinata dall'avvocato C.,",
    "contro",
    "Consiglio di Stato del Cantone Ticino, resistente.",
    "Oggetto",
    "revoca del permesso di dimora,",
    "ricorso di diritto amministrativo contro la decisione emessa il 13 settembre 2006 dal Tribunale amministrativo del Cantone Ticino.",
    "Per questi motivi, il Tribunale federale pronuncia:",
    "1.",
    "Il ricorso è respinto.",
]


def test_codebook_mappings_from_docref_and_dates() -> None:
    assert proc_type_from_docref("5A_643/2017") == "Civil"
    assert division_from_docref("5A_643/2017", "2018-05-03") == "2. Civil"
    assert division_type_from_division("2. Civil") == "Civil"
    assert division_from_docref("8C_1/2024", "2024-01-05") == "4. Public"
    assert days_between("2018-05-03", "2017-08-16") == 260


def test_extract_docref_prefers_registry_docid_for_merged_cases() -> None:
    paragraphs = [
        "2C_889/2020, 2C_890/2020",
        "Arrêt du 4 novembre 2020",
    ]
    registry_record = {"docid": "aza://04-11-2020-2C_890-2020"}

    assert extract_docref(paragraphs, registry_record) == "2C_890/2020"


def test_extract_judges_multilingual_blocks() -> None:
    assert extract_judges(GERMAN_PARAGRAPHS) == (
        3,
        ["Lustenberger", "Borella", "Seiler"],
    )
    assert extract_judges(FRENCH_PARAGRAPHS) == (
        3,
        ["von Werdt", "Escher", "Herrmann"],
    )
    assert extract_judges(FRENCH_SINGLE_JUDGE_PARAGRAPHS) == (1, ["Corboz"])
    assert extract_judges(ITALIAN_PARAGRAPHS) == (
        3,
        ["Merkli", "Wurzburger", "Müller"],
    )


def test_source_date_and_canton_from_issue() -> None:
    issue = (
        "Beschwerde gegen den Entscheid des Sozialversicherungsgerichts "
        "des Kantons Zürich vom 15. März 2007."
    )
    assert extract_source_date(issue) == "2007-03-15"
    assert extract_source_canton(issue) == "ZH"

    french_issue = (
        "recours contre l'arrêt du Tribunal administratif de la République "
        "et canton de Genève du 19 juin 2007."
    )
    assert extract_source_date(french_issue) == "2007-06-19"
    assert extract_source_canton(french_issue) == "GE"

    federal_issue = (
        "Beschwerde gegen den Entscheid des Bundesstrafgerichts, "
        "Strafkammer, vom 30. November 2010."
    )
    assert extract_source_date(federal_issue) == "2010-11-30"
    assert extract_source_canton(federal_issue) == "CH"


def test_source_date_ignores_later_procedural_dates() -> None:
    issue = (
        "Arbeitslosenversicherung, Beschwerde gegen den Entscheid des "
        "Verwaltungsgerichts des Kantons Bern vom 20. August 2010. "
        "Nach Einsicht in die Beschwerde vom 31. August 2010 und die Eingabe "
        "vom 2. September 2010."
    )
    assert extract_source_date(issue) == "2010-08-20"


def test_french_participants_marker_and_safe_party_classification() -> None:
    paragraphs = [
        "Participants à la procédure",
        "X.________, représenté par Me Dominique Warluzel, avocat,",
        "recourant,",
        "contre",
        "Procureur général du canton de Genève, route de Chancy 6B,",
        "intimé.",
        "Objet",
    ]

    block, appellant, respondent = extract_party_block(paragraphs)

    assert block is not None
    assert classify_party(appellant) == "natural"
    assert classify_party(respondent) == "state"
    assert classify_party("Armin Sahli, Rechtsanwalt") == "natural"
    assert classify_party("Y.________SA") == "legal"


def test_merged_cases_uses_header_not_body_citations() -> None:
    paragraphs = [
        "Tribunal fédéral",
        "8C_676/2010",
        "Urteil vom 11. Februar 2011",
        "Besetzung",
    ]
    body = "Die Rechtsprechung erwähnt auch 9C_836/2008 und 6B_493/2007."
    assert not extract_merged_cases("8C_676/2010", body, paragraphs)

    merged_paragraphs = [
        "Tribunal fédéral",
        "6B_482/2007, 6B_483/2007,",
        "6B_176/2008, 6B_180/2008",
    ]
    assert extract_merged_cases("6B_482/2007", "", merged_paragraphs)


def test_citation_formatting_matches_scd_conventions() -> None:
    cited_bger, n_cited_bger, cited_bge, n_cited_bge = extract_citations(
        "Urteile 1P.639/2004 und 4A.23/2008; BGE 133 IV 286; ATF 134 I 83.",
        "1C_250/2007",
    )

    assert cited_bger == "1C_250/2007;1P.639/2004;4A.23/2008"
    assert n_cited_bger == 3
    assert cited_bge == "133 IV 286;134 I 83"
    assert n_cited_bge == 2


def test_outcome_and_binary_outcome() -> None:
    assert extract_outcome(GERMAN_PARAGRAPHS) == "rejected"
    assert outcome_binary("rejected") is False
    assert extract_outcome(FRENCH_PARAGRAPHS) == "granted"
    assert outcome_binary("granted") is True
    assert extract_outcome(ITALIAN_PARAGRAPHS) == "rejected"
    assert outcome_binary("writeoff") is None


def test_additional_mock_outcome_phrases() -> None:
    assert extract_outcome(["Demnach erkennt das Bundesgericht:", "Die Beschwerde wird teilweise gutgeheissen."]) == "partly granted"
    assert extract_outcome(["Par ces motifs:", "Le recours est irrecevable."]) == "inadmissible"
    assert extract_outcome(["Demnach verfügt das Bundesgericht:", "Das Verfahren wird als gegenstandslos abgeschrieben."]) == "writeoff"


def test_build_base_annotation_emits_all_requested_fields() -> None:
    record = build_base_annotation(
        extracted_record={
            "html_id": "example",
            "raw_html_path": "data/raw/judgments/64/example.html",
            "paragraphs": GERMAN_PARAGRAPHS,
            "text": "\n".join(GERMAN_PARAGRAPHS),
        },
        registry_record={
            "url": "https://example.test",
            "docid": "aza://06-09-2007-9C_161-2007",
            "decision_date": "2007-09-06",
            "language": "de",
        },
    )

    assert record["docref"] == "9C_161/2007"
    assert record["date"] == "2007-09-06"
    assert record["year"] == 2007
    assert record["n_judges"] == 3
    assert record["topic"] == "Berufliche Vorsorge"
    assert record["source_date"] == "2007-03-15"
    assert record["source_canton"] == "ZH"
    assert record["proc_duration"] == 175
    assert record["outcome"] == "rejected"
    assert record["outcome_binary"] is False
    assert record["doi_version"] == DOI_VERSION
    assert record["judge_names"] == ["Lustenberger", "Borella", "Seiler"]


def test_build_base_annotation_handles_italian_example() -> None:
    record = build_base_annotation(
        extracted_record={
            "html_id": "italian",
            "raw_html_path": "data/raw/judgments/db/example.html",
            "paragraphs": ITALIAN_PARAGRAPHS,
            "text": "\n".join(ITALIAN_PARAGRAPHS),
        },
        registry_record={
            "url": "https://example.test/it",
            "docid": "aza://27-03-2007-2A.628-2006",
            "decision_date": "2007-03-27",
            "language": "it",
        },
    )

    assert record["docref"] == "2A_628/2006"
    assert record["language"] == "it"
    assert record["source_date"] == "2006-09-13"
    assert record["source_canton"] == "TI"
    assert record["app_represented"] is True
    assert record["resp_class"] == "state"
    assert record["outcome"] == "rejected"


def test_build_base_annotation_handles_french_single_judge_case() -> None:
    record = build_base_annotation(
        extracted_record={
            "html_id": "single-judge",
            "raw_html_path": "data/raw/judgments/00/single.html",
            "paragraphs": FRENCH_SINGLE_JUDGE_PARAGRAPHS,
            "text": "\n".join(FRENCH_SINGLE_JUDGE_PARAGRAPHS),
        },
        registry_record={
            "url": "https://example.test/fr",
            "docid": "aza://06-06-2008-4D_46-2008",
            "decision_date": "2008-06-06",
            "language": "fr",
        },
    )

    assert record["n_judges"] == 1
    assert record["judge_names"] == ["Corboz"]
    assert record["issue"] == (
        "assistance judiciaire gratuite, recours constitutionnel contre l'arrêt "
        "rendu le 1er avril 2008 par la Cour civile du Tribunal cantonal du canton du Jura."
    )
    assert record["source_date"] == "2008-04-01"


def test_mock_llm_classification_updates_missing_fields() -> None:
    classification = LlmClassification.model_validate_json(
        mock_classification_json(
            area_detailed="Vertragsrecht",
            area_intermediate="Obligationenrecht und Handelsrecht",
            area_general="Privatrecht",
            app_class="legal",
            resp_class="natural",
            outcome="partly granted",
            confidence=0.7,
            evidence="short evidence",
        )
    )
    annotation: dict[str, Any] = {
        "area_detailed": None,
        "area_intermediate": None,
        "area_general": None,
        "app_class": None,
        "resp_class": None,
        "outcome": None,
        "outcome_binary": None,
        "confidence": {},
        "evidence": {},
    }

    apply_llm_classification(annotation, classification)

    assert annotation["area_detailed"] == "Vertragsrecht"
    assert annotation["outcome"] == "partly granted"
    assert annotation["outcome_binary"] is True
    assert annotation["confidence"]["area_detailed"] == 0.7


def test_mock_llm_classification_does_not_overwrite_rule_fields() -> None:
    classification = LlmClassification.model_validate_json(
        mock_classification_json(
            area_detailed="Vertragsrecht",
            area_intermediate="Obligationenrecht und Handelsrecht",
            area_general="Privatrecht",
            app_class="legal",
            resp_class="natural",
            outcome="granted",
            confidence=0.9,
            evidence="model evidence",
        )
    )
    annotation: dict[str, Any] = {
        "area_detailed": "Berufliche Vorsorge",
        "area_intermediate": "Sozialversicherungsrecht",
        "area_general": "Öffentliches Recht",
        "app_class": "natural",
        "resp_class": "state",
        "outcome": "rejected",
        "outcome_binary": False,
        "confidence": {},
        "evidence": {},
    }

    apply_llm_classification(annotation, classification)

    assert annotation["area_detailed"] == "Berufliche Vorsorge"
    assert annotation["app_class"] == "natural"
    assert annotation["outcome"] == "rejected"
    assert annotation["outcome_binary"] is False
    assert annotation["confidence"] == {}
