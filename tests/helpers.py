import sys
import tempfile
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from aiterm.core.config import Config  # noqa: E402


def tmpdir():
    return Path(tempfile.mkdtemp(prefix="aiterm-test-"))


def cfg(**kw):
    c = Config()
    c.use_linters = False
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def copy_example(name: str) -> Path:
    d = tmpdir() / name
    shutil.copytree(ROOT / "examples" / name, d, ignore=shutil.ignore_patterns(".aiterm", "__pycache__"))
    return d
