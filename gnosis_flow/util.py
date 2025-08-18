import os
import sys
from pathlib import Path


def project_root_from_cwd() -> Path:
    return Path(os.getcwd())


def ensure_state_dir(root: Path) -> Path:
    state = root / ".gnosis-flow"
    state.mkdir(exist_ok=True)
    return state


def is_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def add_to_gitignore(root: Path, entry: str) -> bool:
    gi = root / ".gitignore"
    if gi.exists():
        content = gi.read_text(encoding="utf-8", errors="ignore").splitlines()
        if any(line.strip() == entry for line in content):
            return False
        content.append(entry)
        gi.write_text("\n".join(content) + "\n", encoding="utf-8")
        return True
    else:
        gi.write_text(entry + "\n", encoding="utf-8")
        return True

