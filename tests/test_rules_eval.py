from pathlib import Path

from gnosis_flow.rules import default_rules_yaml, load_rules
import yaml


def test_rules_match_error_line(tmp_path: Path):
    data = yaml.safe_load(default_rules_yaml())
    # Write to temp rules file and load
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(yaml.dump(data), encoding="utf-8")
    rules = load_rules(rules_path)
    from gnosis_flow.rules import evaluate_log_line
    hits = evaluate_log_line(Path("/var/log/app.log"), "ERROR: database timeout", rules)
    assert any(h.get("type") in ("regex", "fuzzy") for h in hits)


def test_rules_match_py_change(tmp_path: Path):
    data = yaml.safe_load(default_rules_yaml())
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(yaml.dump(data), encoding="utf-8")
    rules = load_rules(rules_path)
    from gnosis_flow.rules import evaluate_file_text
    text = "def hello(x):\n    return x\n"
    hits = evaluate_file_text(Path("/project/a.py"), text, rules)
    assert len(hits) >= 1

