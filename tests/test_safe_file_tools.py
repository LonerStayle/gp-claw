import pytest

from gp_claw.tools.safe_file import create_safe_file_tools
from gp_claw.security import SecurityViolation


@pytest.fixture
def tools(workspace):
    return create_safe_file_tools(str(workspace))


@pytest.fixture
def file_read(tools):
    return tools[0]


@pytest.fixture
def file_search(tools):
    return tools[1]


@pytest.fixture
def file_list(tools):
    return tools[2]


# --- file_read ---

def test_file_read_returns_content(workspace, file_read):
    (workspace / "hello.txt").write_text("world")
    result = file_read.invoke({"path": "hello.txt"})
    assert result["content"] == "world"
    assert result["size_bytes"] == 5


def test_file_read_blocks_outside_workspace(workspace, file_read):
    with pytest.raises(Exception):
        file_read.invoke({"path": "/etc/passwd"})


# --- file_search ---

def test_file_search_finds_by_pattern(workspace, file_search):
    (workspace / "data.xlsx").touch()
    (workspace / "report.xlsx").touch()
    (workspace / "notes.txt").touch()
    result = file_search.invoke({"pattern": "*.xlsx"})
    names = {f["name"] for f in result["files"]}
    assert names == {"data.xlsx", "report.xlsx"}


def test_file_search_respects_directory(workspace, file_search):
    sub = workspace / "sub"
    sub.mkdir()
    (sub / "a.txt").touch()
    (workspace / "b.txt").touch()
    result = file_search.invoke({"pattern": "*.txt", "directory": "sub"})
    assert len(result["files"]) == 1
    assert result["files"][0]["name"] == "a.txt"


# --- file_list ---

def test_file_list_returns_entries(workspace, file_list):
    (workspace / "file.txt").write_text("hello")
    (workspace / "subdir").mkdir()
    result = file_list.invoke({"directory": "."})
    names = {e["name"] for e in result["entries"]}
    assert "file.txt" in names
    assert "subdir" in names


def test_file_list_shows_types(workspace, file_list):
    (workspace / "f.txt").touch()
    (workspace / "d").mkdir()
    result = file_list.invoke({"directory": "."})
    entries = {e["name"]: e["type"] for e in result["entries"]}
    assert entries["f.txt"] == "file"
    assert entries["d"] == "dir"
