from mellowlang.mmg_runtime import parse_mmg_spec, mmg_status


def test_parse_mmg_spec_basic():
    spec = parse_mmg_spec(
        "keep app = mmg.app(title: \"Demo\", width: 800, height: 600, clear: \"#111111\")\n"
        "mmg.rect(app, 10, 20, 30, 40, fill: \"#ff00aa\")\n"
        "mmg.text(app, 5, 6, \"Hi\", size: 18)\n"
    )
    assert spec["title"] == "Demo"
    assert spec["width"] == 800
    assert spec["height"] == 600
    assert spec["clear"] == "#111111"
    assert len(spec["draw"]) == 2


def test_mmg_status_shape():
    payload = mmg_status()
    assert payload["engine"] == "mellow-magic-graphics"
    assert "backend" in payload
