import pytest

from gp_claw.tools.dangerous_file import create_dangerous_file_tools


@pytest.fixture
def tools(workspace):
    return create_dangerous_file_tools(str(workspace))


@pytest.fixture
def file_write(tools):
    return tools[0]


@pytest.fixture
def file_delete(tools):
    return tools[1]


@pytest.fixture
def file_move(tools):
    return tools[2]


# --- file_write ---

def test_file_write_creates_new_file(workspace, file_write):
    result = file_write.invoke({"path": "new.txt", "content": "hello"})
    assert result["action"] == "created"
    assert (workspace / "new.txt").read_text() == "hello"


def test_file_write_overwrites_existing(workspace, file_write):
    (workspace / "exist.txt").write_text("old")
    result = file_write.invoke({"path": "exist.txt", "content": "new"})
    assert result["action"] == "overwritten"
    assert (workspace / "exist.txt").read_text() == "new"


def test_file_write_creates_parent_dirs(workspace, file_write):
    result = file_write.invoke({"path": "sub/deep/file.txt", "content": "nested"})
    assert result["action"] == "created"
    assert (workspace / "sub" / "deep" / "file.txt").read_text() == "nested"


def test_file_write_blocks_outside_workspace(workspace, file_write):
    with pytest.raises(Exception):
        file_write.invoke({"path": "/etc/hacked", "content": "bad"})


# --- file_delete ---

def test_file_delete_removes_file(workspace, file_delete):
    target = workspace / "delete_me.txt"
    target.write_text("bye")
    result = file_delete.invoke({"path": "delete_me.txt"})
    assert not target.exists()
    assert result["size_bytes"] > 0


def test_file_delete_nonexistent_raises(workspace, file_delete):
    with pytest.raises(Exception):
        file_delete.invoke({"path": "no_such_file.txt"})


# --- file_move ---

def test_file_move_renames(workspace, file_move):
    (workspace / "old.txt").write_text("data")
    result = file_move.invoke({"source": "old.txt", "destination": "new.txt"})
    assert not (workspace / "old.txt").exists()
    assert (workspace / "new.txt").read_text() == "data"


def test_file_move_to_subdir(workspace, file_move):
    (workspace / "src.txt").write_text("data")
    result = file_move.invoke({"source": "src.txt", "destination": "sub/dst.txt"})
    assert (workspace / "sub" / "dst.txt").read_text() == "data"


def test_file_move_nonexistent_raises(workspace, file_move):
    with pytest.raises(Exception):
        file_move.invoke({"source": "ghost.txt", "destination": "dest.txt"})
