import shutil
import subprocess
from pathlib import Path

import pytest

from uepyscripts.tools.ugs.commit_history import CommitHistory, CommitHistoryError

UNREACHABLE = "file:///nowhere/at/all"


GIT_TEST_CONFIG = ("commit.gpgsign=false", "core.autocrlf=false", "user.name=Test", "user.email=test@example.com")


def git(cwd: Path, *args: str) -> str:
    config = [arg for setting in GIT_TEST_CONFIG for arg in ("-c", setting)]
    return subprocess.run(
        ["git", *config, *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def commit(repo: Path, rel: str, content: str) -> str:
    """Writes `content` to `rel` and commits it. Returns the new commit's SHA."""
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"{rel}: {content}")
    return git(repo, "rev-parse", "HEAD")


def clone(origin: Path, destination: Path, *, depth: int | None = None) -> Path:
    depth_args = ["--depth", str(depth)] if depth else []
    git(origin.parent, "clone", "-q", *depth_args, origin.as_uri(), str(destination))
    return destination


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keeps Jenkins' variables and any repository around tmp_path out of the tests."""
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.delenv("GIT_BRANCH", raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))


@pytest.fixture(scope="module")
def origin_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A repository with five commits on main, built once: each git process is slow on Windows."""
    repo = tmp_path_factory.mktemp("template") / "origin"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    for i in range(1, 6):
        commit(repo, "Engine/Binaries/Win64/Engine.dll", f"v{i}")
    return repo


@pytest.fixture
def origin(origin_template: Path, tmp_path: Path) -> Path:
    """A copy of the template, so a test can change it."""
    return Path(shutil.copytree(origin_template, tmp_path / "origin"))


def origin_shas(origin: Path) -> list[str]:
    return git(origin, "log", "--format=%H", "main").splitlines()


# ---- Opening --------------------------------------------------------


def test_a_folder_that_is_not_a_repository_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "plain"
    folder.mkdir()

    with pytest.raises(CommitHistoryError, match="not a git repository"):
        CommitHistory(folder)


# ---- Current commit and ancestry ------------------------------------


def test_the_current_commit_is_head_unless_jenkins_sets_git_commit(origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history = CommitHistory(clone(origin, tmp_path / "clone"))
    shas = origin_shas(origin)

    assert history.current_commit() == shas[0]

    monkeypatch.setenv("GIT_COMMIT", shas[2])
    assert history.current_commit() == shas[2]


def test_the_ancestry_is_newest_first_and_starts_at_the_current_commit(origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history = CommitHistory(clone(origin, tmp_path / "clone"))
    shas = origin_shas(origin)

    assert history.ancestry() == shas

    monkeypatch.setenv("GIT_COMMIT", shas[2])
    assert history.ancestry() == shas[2:]


def test_a_git_commit_missing_from_the_history_is_refused(origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history = CommitHistory(clone(origin, tmp_path / "clone"))
    monkeypatch.setenv("GIT_COMMIT", "0" * 40)

    with pytest.raises(CommitHistoryError, match="GIT_COMMIT"):
        history.ancestry()


def test_a_shallow_clone_is_deepened_before_its_ancestry_is_read(origin: Path, tmp_path: Path) -> None:
    history = CommitHistory(clone(origin, tmp_path / "clone", depth=1))

    assert history.is_shallow()
    assert history.ancestry() == origin_shas(origin)


def test_a_shallow_clone_whose_remote_is_unreachable_keeps_its_local_history(origin: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    repo = clone(origin, tmp_path / "clone", depth=1)
    git(repo, "remote", "set-url", "origin", UNREACHABLE)

    assert CommitHistory(repo).ancestry() == origin_shas(origin)[:1]
    assert "Could not deepen" in caplog.text


# ---- Remote branches ------------------------------------------------


def test_remote_branch_ancestries_are_tip_first_and_skip_deleted_branches(origin: Path, tmp_path: Path) -> None:
    git(origin, "switch", "-q", "-c", "feature")
    feature_tip = commit(origin, "feature.txt", "work")
    git(origin, "switch", "-q", "-c", "gone")
    git(origin, "switch", "-q", "main")
    repo = clone(origin, tmp_path / "clone")
    git(origin, "branch", "-q", "-D", "gone")
    shas = origin_shas(origin)

    ancestries = CommitHistory(repo).remote_branch_ancestries()

    assert ancestries == {"main": shas, "feature": [feature_tip, *shas]}


def test_a_non_default_remote_is_used_for_branches_and_deepening(origin: Path, tmp_path: Path) -> None:
    repo = clone(origin, tmp_path / "clone", depth=1)
    git(repo, "remote", "set-url", "origin", UNREACHABLE)
    git(repo, "remote", "add", "upstream", origin.as_uri())
    history = CommitHistory(repo, remote="upstream")

    assert history.ancestry() == origin_shas(origin)
    assert set(history.remote_branch_ancestries()) == {"main"}


def test_a_failing_git_command_is_a_commit_history_error(origin: Path, tmp_path: Path) -> None:
    history = CommitHistory(clone(origin, tmp_path / "clone"), remote="nope")

    with pytest.raises(CommitHistoryError, match="nope"):
        history.remote_branch_ancestries()


# ---- Branch ---------------------------------------------------------


@pytest.mark.parametrize(("git_branch", "expected"), [("origin/feature", "feature"), ("release", "release")])
def test_the_branch_comes_from_jenkins_git_branch_when_set(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_branch: str, expected: str
) -> None:
    monkeypatch.setenv("GIT_BRANCH", git_branch)

    assert CommitHistory(clone(origin, tmp_path / "clone")).branch() == expected


def test_the_branch_is_the_checked_out_one(origin: Path, tmp_path: Path) -> None:
    assert CommitHistory(clone(origin, tmp_path / "clone")).branch() == "main"


def test_a_detached_head_is_named_after_a_remote_branch_pointing_at_it_not_the_remote_head(origin: Path, tmp_path: Path) -> None:
    repo = clone(origin, tmp_path / "clone")
    git(repo, "switch", "-q", "--detach")
    git(repo, "branch", "-q", "-D", "main")

    assert CommitHistory(repo).branch() == "main"  # from origin/main, skipping origin/HEAD


def test_a_detached_head_keeps_the_full_name_of_a_local_branch_pointing_at_it(origin: Path, tmp_path: Path) -> None:
    repo = clone(origin, tmp_path / "clone")
    git(repo, "switch", "-q", "--detach", "HEAD~1")
    git(repo, "branch", "-q", "feature/foo")

    assert CommitHistory(repo).branch() == "feature/foo"


def test_a_detached_head_no_ref_points_at_is_named_head(origin: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    repo = clone(origin, tmp_path / "clone")
    git(repo, "switch", "-q", "--detach", "HEAD~1")

    assert CommitHistory(repo).branch() == "HEAD"
    assert "Could not resolve current branch" in caplog.text


# ---- Uncommitted changes --------------------------------------------


def test_uncommitted_changes_are_only_reported_inside_the_folder(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "Engine/Source/Engine.cpp", "v1")
    commit(repo, "README.md", "v1")
    history = CommitHistory(repo)

    assert not history.has_uncommitted_changes("Engine/Source")

    (repo / "README.md").write_text("v2")
    assert not history.has_uncommitted_changes("Engine/Source")

    (repo / "Engine/Source/Engine.cpp").write_text("v2")
    assert history.has_uncommitted_changes("Engine/Source")
