from mellowlang.mmg_runtime import parse_mmg_spec, mmg_status


def test_parse_render_core_spec():
    spec = parse_mmg_spec(
        'keep app = mmg.app(title: "Demo", width: 800, height: 600, clear: "#111111")\n'
        'mmg.scene(app, "main")\n'
        'mmg.camera(app, x: 10, y: 20, zoom: 1.5, follow: "hero")\n'
        'mmg.texture(app, "hero", source: "assets/hero.png")\n'
        'mmg.sprite(app, "hero", x: 100, y: 120, w: 64, h: 64, vx: 2, vy: 0)\n'
        'mmg.on(app, "key", "Escape", "close")\n'
        'mmg.frame(app, fps: 30)\n'
    )
    assert spec['title'] == 'Demo'
    assert spec['camera']['zoom'] == 1.5
    assert spec['frame']['fps'] == 30
    assert spec['textures'][0]['id'] == 'hero'
    assert spec['scenes'][0]['sprites'][0]['texture'] == 'hero'
    assert spec['events'][0]['action']['type'] == 'close'
    assert spec['render_graph']['passes'][1]['name'] == 'scene'


def test_mmg_status_render_core_features():
    payload = mmg_status()
    assert payload['engine'] == 'mellow-magic-graphics'
    assert 'render-graph' in payload['features']
