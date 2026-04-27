from __future__ import annotations

from ccc.cli import main


def test_cli_init_creates_state(tmp_path):
    rc = main(
        [
            "--root",
            str(tmp_path),
            "init",
            "--prompt",
            "Build it",
            "--style",
            "- 4 spaces",
            "--phase",
            "MVP",
        ]
    )
    assert rc == 0
    state_file = tmp_path / ".ccc" / "state.json"
    assert state_file.exists()
    contents = state_file.read_text()
    assert "Build it" in contents
    assert "MVP" in contents


def test_cli_todo_workflow(tmp_path):
    main(["--root", str(tmp_path), "init"])
    rc = main(["--root", str(tmp_path), "todo", "Write CLI"])
    assert rc == 0
    rc = main(["--root", str(tmp_path), "status"])
    assert rc == 0


def test_cli_sprint_phase(tmp_path):
    main(["--root", str(tmp_path), "init"])
    rc = main(["--root", str(tmp_path), "phase", "MVP"])
    assert rc == 0
    rc = main(["--root", str(tmp_path), "sprint", "start", "scaffolding"])
    assert rc == 0
    rc = main(["--root", str(tmp_path), "sprint", "complete", "--notes", "done"])
    assert rc == 0
