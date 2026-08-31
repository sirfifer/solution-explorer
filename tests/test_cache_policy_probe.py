import importlib.util
from pathlib import Path


def _probe_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "cache-policy-probe.py"
    spec = importlib.util.spec_from_file_location("_cache_policy_probe", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cache_probe_prices_each_ttl_against_the_uncached_counterfactual():
    probe = _probe_module()
    result = probe._cache_economics({
        "fresh": 10,
        "write": 200,
        "write_1h": 100,
        "write_5m": 100,
        "write_unknown": 0,
        "read": 300,
        "out": 99,
    })
    assert result == {
        "known": True,
        "actual_input_equivalent": 365.0,
        "uncached_input_equivalent": 510,
        "net_input_equivalent": -145.0,
        "saving_fraction": 0.2843,
    }


def test_cache_probe_refuses_to_invent_economics_for_unknown_write_ttl():
    probe = _probe_module()
    result = probe._cache_economics({
        "fresh": 0,
        "write": 100,
        "write_1h": 0,
        "write_5m": 0,
        "write_unknown": 100,
        "read": 20,
        "out": 0,
    })
    assert result["known"] is False
    assert result["net_input_equivalent"] is None
    assert result["uncached_input_equivalent"] == 120
