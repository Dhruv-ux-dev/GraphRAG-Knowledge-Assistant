"""Unit tests for the GraphRAG Knowledge Assistant. No Neo4j or Ollama required."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app  # noqa: E402

DOC = app.DEMO_DOCUMENTS["CloudEngine Specification"]


class FakeLLM:
    """Stand-in for the Ollama client that returns canned responses."""

    def __init__(self, extraction=None, answer=""):
        self.extraction = extraction
        self.answer = answer
        self.prompts = []

    def chat(self, model, messages, **kwargs):
        self.prompts.append(messages[0]["content"])
        if kwargs.get("format") == "json":
            content = self.extraction if isinstance(self.extraction, str) else json.dumps(self.extraction)
            return {"message": {"content": content}}
        return {"message": {"content": self.answer}}


class FakeStore:
    """Stand-in for Neo4jGraphStore with a fixed tiny graph."""

    def __init__(self, entries=None, neighbors=None):
        self.entries = entries or []
        self.neighbors = neighbors or {}

    def find_entry_nodes(self, question, limit=app.MAX_ENTRY_NODES):
        return self.entries

    def fetch_hops_context(self, node_id, depth=2, limit=25):
        return self.neighbors.get(node_id, [])


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(app, "inference_client", fake)
    return fake


# ---- Normalization -------------------------------------------------------------

def test_normalize_text_strips_case_and_punctuation():
    assert app.normalize_text("  CodeSync's   Team! ") == "codesync s team"


def test_node_id_is_stable_across_spellings():
    assert app.make_node_id("Dhruv Mittal") == app.make_node_id("dhruv  mittal")
    assert app.make_node_id("Dhruv Mittal") != app.make_node_id("CloudEngine")


@pytest.mark.parametrize("raw,expected", [
    ("works for", "WORKS_FOR"),
    ("designed-by", "DESIGNED_BY"),
    ("", "RELATED_TO"),
    (None, "RELATED_TO"),
])
def test_normalize_label(raw, expected):
    assert app.normalize_label(raw, "RELATED_TO") == expected


def test_extract_search_terms_drops_stopwords_and_stems_plurals():
    terms = app.extract_search_terms("What is CloudEngine and who backs its developers?")
    assert terms == ["cloudengine", "back", "developer"]


def test_find_snippet_returns_sentence_mentioning_entity():
    snippet = app.find_snippet(DOC, "Dhruv Mittal")
    assert "architected by Dhruv Mittal" in snippet
    assert "CloudEngine is an automated" not in snippet


def test_find_snippet_falls_back_to_document_start():
    assert app.find_snippet(DOC, "Nonexistent Entity").startswith("CloudEngine is an automated")


# ---- Extraction ------------------------------------------------------------------

def test_extraction_tolerates_missing_fields_and_messy_names(llm):
    llm.extraction = {
        "nodes": [
            {"name": "CloudEngine", "type": "technology", "summary": "Deployment framework"},
            {"name": "Dhruv Mittal", "type": "PERSON"},            # no summary
            {"name": "", "type": "PERSON"},                         # no name -> skipped
            {"type": "ORGANIZATION"},                               # no name -> skipped
            "San Francisco",                                        # bare string
            {"name": "cloudengine", "type": "TECHNOLOGY"},          # duplicate
        ],
        "edges": [
            {"source": "dhruv mittal", "target": "CloudEngine", "type": "architected"},
            {"source": "CloudEngine", "target": "CloudEngine", "type": "SELF"},   # self-loop -> skipped
            {"source": "CloudEngine"},                                           # no target -> skipped
            {"source": "Dhruv Mittal", "target": "CloudEngine", "type": "ARCHITECTED"},  # duplicate
        ],
    }
    nodes, edges = app.parse_graph_elements_via_llm(DOC, "Spec")

    assert [n.display_name for n in nodes] == ["CloudEngine", "Dhruv Mittal", "San Francisco"]
    assert nodes[0].category == "TECHNOLOGY"
    assert nodes[1].summary == ""
    assert nodes[2].category == "CONCEPT"
    assert "Dhruv Mittal" in nodes[1].text_snippet

    assert len(edges) == 1
    assert edges[0].source_node == "Dhruv Mittal"   # canonical spelling from the node list
    assert edges[0].edge_type == "ARCHITECTED"


def test_extraction_accepts_alternative_keys(llm):
    llm.extraction = {
        "entities": [{"name": "A", "category": "person"}, {"name": "B", "label": "Organization"}],
        "relationships": [{"from": "A", "to": "B", "relation": "works for"}],
    }
    nodes, edges = app.parse_graph_elements_via_llm("A works for B.", "Doc")
    assert [(n.display_name, n.category) for n in nodes] == [("A", "PERSON"), ("B", "ORGANIZATION")]
    assert edges[0].edge_type == "WORKS_FOR"


def test_extraction_rejects_invalid_json(llm):
    llm.extraction = "not json at all"
    with pytest.raises(app.ExtractionError, match="invalid JSON"):
        app.parse_graph_elements_via_llm(DOC, "Spec")


def test_extraction_rejects_non_object(llm):
    llm.extraction = ["a", "b"]
    with pytest.raises(app.ExtractionError, match="JSON object"):
        app.parse_graph_elements_via_llm(DOC, "Spec")


def test_extraction_reports_unreachable_ollama(monkeypatch):
    class Down:
        def chat(self, **kwargs):
            raise ConnectionError("connection refused")

    monkeypatch.setattr(app, "inference_client", Down())
    with pytest.raises(app.ExtractionError, match="Could not reach Ollama"):
        app.parse_graph_elements_via_llm(DOC, "Spec")


# ---- Retrieval and answering -------------------------------------------------------

ENTRY = {
    "id": "n1", "name": "CloudEngine", "summary": "Deployment framework", "type": "TECHNOLOGY",
    "documents": ["Spec"], "snippets": ["CloudEngine is an automated deployment framework."],
    "relevance": 13, "name_match": True,
}
NEIGHBOR = {
    "id": "n2", "name": "Dhruv Mittal", "summary": "Architect", "type": "PERSON",
    "documents": ["Spec", "Overview"], "snippets": ["Architected by Dhruv Mittal.", "Led by Dhruv Mittal."],
    "hops": 1, "path_names": ["CloudEngine", "Dhruv Mittal"],
    "relations": ["Dhruv Mittal -[ARCHITECTED]-> CloudEngine: architected the system"],
}


def test_answer_with_valid_and_invalid_citations(llm):
    llm.answer = "CloudEngine is a framework [1] architected by Dhruv Mittal [2]. Also [7]."
    store = FakeStore([ENTRY], {"n1": [NEIGHBOR]})

    result = app.run_attributed_graph_rag("Who built CloudEngine?", store)

    assert [s.claim_text for s in result.sources] == ["[1] CloudEngine", "[2] Dhruv Mittal"]
    assert result.sources[0].score == 1.0
    assert result.sources[1].score == 0.5
    assert result.sources[1].path_trace == ["CloudEngine", "Dhruv Mittal"]
    assert result.sources[1].doc_source == "Spec, Overview"
    assert "[Overview] Led by Dhruv Mittal." in result.sources[1].reference_text
    assert any("[7]" in step for step in result.execution_steps)

    prompt = llm.prompts[-1]
    assert "[1] CloudEngine (TECHNOLOGY)" in prompt
    assert "ARCHITECTED" in prompt
    # Entry node also lists its direct relationships
    first_item = prompt.split("CONTEXT:")[1].split("\n[2]")[0]
    assert "Relationships: Dhruv Mittal -[ARCHITECTED]-> CloudEngine" in first_item


def test_no_matching_nodes_skips_llm(llm):
    result = app.run_attributed_graph_rag("What is the capital of France?", FakeStore())
    assert "No entities in the knowledge graph match" in result.content
    assert result.sources == []
    assert llm.prompts == []


def test_answer_generation_failure_is_reported(monkeypatch):
    class Down:
        def chat(self, **kwargs):
            raise RuntimeError("model not found")

    monkeypatch.setattr(app, "inference_client", Down())
    result = app.run_attributed_graph_rag("CloudEngine?", FakeStore([ENTRY]))
    assert "model not found" in result.content
    assert result.sources == []


def test_neighbors_are_deduplicated_across_entry_nodes(llm):
    llm.answer = "Answer [1]."
    second_entry = dict(NEIGHBOR, relevance=13, name_match=True)
    store = FakeStore([ENTRY, second_entry], {"n1": [NEIGHBOR], "n2": [dict(ENTRY, hops=1, path_names=["Dhruv Mittal", "CloudEngine"], relations=[])]})
    entries, _ = app.collect_graph_context("CloudEngine and Dhruv Mittal", store)
    assert sorted(e["name"] for e in entries) == ["CloudEngine", "Dhruv Mittal"]
    assert all(e["hops"] == 0 for e in entries)
