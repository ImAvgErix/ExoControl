from aether.exec_engine import AetherExecEngine, MAX_STEPS


class StubController:
    def status(self):
        return {"ok": True, "driver": "stub"}

    def list_windows(self):
        return [{"title": "One"}]

    def stats(self, reset=False):
        return {"ok": True, "reset": reset}


def test_parse_accepts_array_and_steps_object():
    assert AetherExecEngine.parse('[{"op":"status"}]') == [{"op": "status"}]
    assert AetherExecEngine.parse({"steps": [{"op": "windows"}]}) == [{"op": "windows"}]


def test_parse_rejects_invalid_and_oversized_scripts():
    for value in ("not json", {}, ["status"]):
        try:
            AetherExecEngine.parse(value)
            assert False, f"expected rejection for {value!r}"
        except ValueError:
            pass
    try:
        AetherExecEngine.parse([{"op": "status"}] * (MAX_STEPS + 1))
        assert False, "expected oversized script rejection"
    except ValueError:
        pass


def test_list_results_do_not_break_failure_detection():
    engine = AetherExecEngine(controller=StubController())
    result = engine.execute([{"op": "windows"}, {"op": "status"}])
    assert result["ok"] is True
    assert result["completed"] == 2
    assert result["steps"][0]["result"] == [{"title": "One"}]


def test_unknown_operation_stops_by_default_but_can_continue():
    engine = AetherExecEngine(controller=StubController())
    stopped = engine.execute([{"op": "missing"}, {"op": "status"}])
    assert stopped["ok"] is False
    assert stopped["completed"] == 1

    continued = engine.execute(
        [{"op": "missing", "stop_on_failure": False}, {"op": "status"}]
    )
    assert continued["completed"] == 2
