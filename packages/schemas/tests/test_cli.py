import json
from pathlib import Path

from schemas.cli import MODELS, export_schemas, main


def test_export_schemas_writes_one_file_per_model(tmp_path: Path) -> None:
    written = export_schemas(tmp_path)

    assert {path.name for path in written} == {f"{name}.schema.json" for name in MODELS}
    for path in written:
        schema = json.loads(path.read_text())
        assert "properties" in schema


def test_main_export_writes_to_custom_out_dir(tmp_path: Path, capsys) -> None:
    main(["export", "--out", str(tmp_path)])

    captured = capsys.readouterr()
    for name in MODELS:
        assert (tmp_path / f"{name}.schema.json").exists()
        assert str(tmp_path / f"{name}.schema.json") in captured.out
