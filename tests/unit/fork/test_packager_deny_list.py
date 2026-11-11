import os
from pathlib import Path

import pytest

from harbor.publisher.packager import Packager

pytestmark = pytest.mark.unit

DENIED_PATHS = [
    ".git/HEAD",
    ".git/objects/ab/cd",
    ".venv/lib/x.py",
    "node_modules/a/index.js",
    ".env",
    ".env.production",
    "environment/.env",
    "tests/.env.local",
    "a.local.json",
    ".claude/settings.local.json",
    ".gitignore",
    "x~",
    "a.swp",
    "a.swo",
    "__pycache__/m.pyc",
    ".DS_Store",
]
ALLOWED_PATHS = [
    ".claude/skills/x/SKILL.md",
    "docs/notes.md",
    "environment/Dockerfile",
    "tests/test.sh",
    "solution/solve.sh",
    ".github/x.yml",
]


def write_file(root: Path, relative_path: str, content: str = "fixture\n") -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture
def task_dir(tmp_path: Path) -> Path:
    root = tmp_path / "task"
    root.mkdir()
    write_file(root, ".gitignore", "!.env\n!*.local.json\n!.venv/\n")
    for relative_path in DENIED_PATHS:
        if relative_path != ".gitignore":
            write_file(root, relative_path)
    for relative_path in ALLOWED_PATHS:
        write_file(root, relative_path)
    return root


@pytest.mark.parametrize("relative_path", DENIED_PATHS)
def test_deny_list_excludes_paths_even_when_gitignore_reincludes_them(
    task_dir: Path, relative_path: str
) -> None:
    collected = {
        path.relative_to(task_dir).as_posix()
        for path in Packager.collect_files(task_dir)
    }

    assert relative_path not in collected


def test_allowed_files_are_packaged(task_dir: Path) -> None:
    collected = {
        path.relative_to(task_dir).as_posix()
        for path in Packager.collect_files(task_dir)
    }

    assert set(ALLOWED_PATHS) <= collected


@pytest.mark.skipif(os.name == "nt", reason="directory symlinks vary on Windows")
def test_directory_symlink_is_not_followed_or_packaged_as_a_file(
    task_dir: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "linked-directory"
    outside.mkdir()
    write_file(outside, "secret.txt")
    link = task_dir / "linked-directory"
    link.symlink_to(outside, target_is_directory=True)

    collected = Packager.collect_files(task_dir)
    relative_paths = {path.relative_to(task_dir).as_posix() for path in collected}

    assert "linked-directory" not in relative_paths
    assert "linked-directory/secret.txt" not in relative_paths


def test_collection_is_sorted_and_stable_across_calls(task_dir: Path) -> None:
    first = Packager.collect_files(task_dir)
    second = Packager.collect_files(task_dir)
    first_relative = [path.relative_to(task_dir).as_posix() for path in first]

    assert first_relative == sorted(first_relative)
    assert second == first


def test_content_hash_ignores_changes_to_denied_files(task_dir: Path) -> None:
    before, _ = Packager.compute_content_hash(task_dir)
    (task_dir / ".env").write_text("changed secret\n")

    after, _ = Packager.compute_content_hash(task_dir)

    assert after == before


def test_content_hash_changes_when_allowed_file_is_added(task_dir: Path) -> None:
    before, _ = Packager.compute_content_hash(task_dir)
    write_file(task_dir, "docs/new-note.md", "new allowed content\n")

    after, _ = Packager.compute_content_hash(task_dir)

    assert after != before
