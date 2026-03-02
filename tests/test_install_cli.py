from pathlib import Path

from clausy import install


def test_build_install_steps_default_includes_playwright():
    steps = install.build_install_steps()
    assert Path(steps[0][0]).name.startswith("python")
    assert steps[0][1:] == ["-m", "venv", ".venv"]
    assert steps[-1][-4:] == ["-m", "playwright", "install", "chromium"]


def test_build_install_steps_can_skip_playwright():
    steps = install.build_install_steps(include_playwright=False)
    flat = [" ".join(s) for s in steps]
    assert not any("playwright install chromium" in line for line in flat)
    assert any("pip install ." in line for line in flat)
