import frameworks.mellow_ui as UI


def test_create_element_basic():
    element = UI.createElement("TextLabel", {"Text": "Hello"})
    assert element.type == "TextLabel"
    assert element.props == {"Text": "Hello"}
    assert element.children == []


def test_children_from_props():
    element = UI.createElement("Frame", {"Children": [UI.createElement("TextLabel", {"Text": "A"})]})
    assert element.type == "Frame"
    assert element.props == {}
    assert len(element.children) == 1


def test_function_component_render():
    def Hello(props):
        return UI.createElement("TextLabel", {"Text": "Hello " + props["name"]})

    tree = UI.render_to_tree(UI.createElement(Hello, {"name": "Mellow"}))
    assert tree == {
        "type": "TextLabel",
        "props": {"Text": "Hello Mellow"},
        "children": [],
    }


def test_root_render_nested_tree():
    def App(props):
        return UI.createElement("Screen", {
            "Name": "Main",
            "Children": [
                UI.createElement("Frame", {
                    "Children": [UI.createElement("TextLabel", {"Text": "Ready"})]
                })
            ],
        })

    root = UI.createRoot("App")
    output = root.render(UI.createElement(App, {}))

    assert output["container"] == "App"
    assert output["tree"]["type"] == "Screen"
    assert output["tree"]["props"] == {"Name": "Main"}
    assert output["tree"]["children"][0]["type"] == "Frame"
    assert output["tree"]["children"][0]["children"][0]["props"]["Text"] == "Ready"


def test_render_to_json_export():
    raw = UI.render_to_json(UI.TextLabel("Export"))
    assert '"type": "TextLabel"' in raw
    assert '"Text": "Export"' in raw


def test_builtin_components():
    root = UI.createRoot("App")
    output = root.render(UI.Screen({
        "Children": [
            UI.TextLabel("Title"),
            UI.Button("Play"),
            UI.ProgressBar(0.5),
        ]
    }))

    children = output["tree"]["children"]
    assert children[0]["type"] == "TextLabel"
    assert children[0]["props"]["Text"] == "Title"
    assert children[1]["type"] == "Button"
    assert children[1]["props"]["Text"] == "Play"
    assert children[2]["type"] == "ProgressBar"
    assert children[2]["props"]["Value"] == 0.5


def test_use_state_object():
    state = UI.useState(0)
    seen = []
    state.subscribe(lambda value: seen.append(value))
    state.set(10)
    assert state.value == 10
    assert seen == [10]
