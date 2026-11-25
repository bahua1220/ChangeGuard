from repolens.analytics import frames
from repolens.methods import extract_methods


def test_new_modified_and_deleted_methods_in_real_history(snapshot):
    _, changes = frames(snapshot)
    new_file = changes[(changes["path"] == "src/mining/reader.py") & (changes["change_type"] == "ADD")].iloc[0]
    assert new_file["method_status"] == "available"
    assert {m["name"] for m in new_file["changed_methods"]} == {"read_metadata"}
    assert {m["version"] for m in new_file["changed_methods"]} == {"after"}
    modified = changes[(changes["path"] == "src/ui/timeline.py") & (changes["change_type"] == "MODIFY")].iloc[0]
    assert {m["version"] for m in modified["changed_methods"]} == {"before", "after"}
    deleted = changes[changes["change_type"] == "DELETE"].iloc[0]
    assert {m["version"] for m in deleted["changed_methods"]} == {"before"}
    readme = changes[changes["path"] == "README.md"].iloc[0]
    assert readme["method_status"] == "unsupported"


def test_parser_failure_is_separate_from_file_stats():
    class Broken:
        language_supported = True

        @property
        def diff_parsed(self):
            raise RuntimeError("parser cannot read this source")

    assert extract_methods(Broken()) == {"method_status": "error", "changed_methods": []}
