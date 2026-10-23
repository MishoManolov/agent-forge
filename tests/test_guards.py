from forge.guards.destructive import check


def test_blocks():
    assert check("rm -rf /")
    assert check("git push --force origin main")


def test_allows():
    assert check("rm -rf ./build") is None
    assert check("git push origin feat") is None


def test_hook_protocol(capsys, monkeypatch):
    import io
    import json

    from forge.guards import hook
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(
        {"tool_name": "terminal", "tool_input": {"command": "git push --force"}})))
    hook.main()
    assert json.loads(capsys.readouterr().out)["decision"] == "block"
