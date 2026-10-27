import pytest

from backend.app.tools.registry import ToolContext, dispatch


@pytest.mark.parametrize("name,args,unexpected", [
    ("zoom_map", {"site_id": ["S01"]}, "site_id"),
    ("highlight_sites", {"site_ids": ["S01"], "result_ids": "r_0001"}, "result_ids"),
])
def test_misspelled_arguments_are_rejected(bundle, name, args, unexpected):
    result = dispatch(name, args, ToolContext(bundle))
    assert result.status == "error"
    assert result.error.code == "invalid_arguments"
    assert unexpected in result.error.hint
    assert result.table is None


def test_dataset_access_rejects_unexpected_filters(bundle):
    result = dispatch("get_dataset", {"dataset_id": "sites", "company_id": "C01"}, ToolContext(bundle))
    assert result.status == "error"
    assert result.error.code == "invalid_arguments"
    assert "company_id" in result.error.hint


@pytest.mark.parametrize("arguments", ["[1]", "5", '"sites"'])
def test_non_object_arguments_are_rejected(bundle, arguments):
    result = dispatch("get_dataset", arguments, ToolContext(bundle))
    assert result.error.code == "invalid_arguments" and result.args == {}


def test_unknown_tool_is_reported_before_argument_parsing(bundle):
    assert dispatch("no_such_tool", "{not json", ToolContext(bundle)).error.code == "unknown_tool"


def test_valid_site_ids_and_portfolio_loading_still_work(bundle):
    ctx = ToolContext(bundle)
    highlighted = dispatch("highlight_sites", {"site_ids": ["S01"]}, ctx)
    loaded = dispatch("get_dataset", {"dataset_id": "sites"}, ctx)
    assert highlighted.status == "ok" and highlighted.data["site_ids"] == ["S01"]
    assert loaded.status == "ok" and loaded.table.total_rows == 13
