from make_release_zip import collect_files


def test_release_selection_includes_statistics_runtime_and_excludes_bytecode(tmp_path):
    runtime_paths = ["app.py", "stats/__init__.py", "stats/ta.py", "stats/tcd.py"]
    for name in [*runtime_paths, "stats/__pycache__/ta.cpython-312.pyc"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n", encoding="utf-8")

    selected = collect_files(tmp_path, use_git_only=False, with_data=False)

    assert {path.relative_to(tmp_path).as_posix() for path in selected} == set(
        runtime_paths
    )
