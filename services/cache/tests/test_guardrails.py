"""Unit tests for the pure evaluate_guardrails function."""

from app.guardrails import evaluate_guardrails

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rule(
    id="r1",
    name="test-rule",
    type="pii",
    action="flag",
    severity="high",
    patterns=None,
    applies_to="input",
    enabled=True,
    mask=None,
):
    cfg = {"patterns": patterns or [r"\bsecret\b"]}
    if mask is not None:
        cfg["mask"] = mask
    return {
        "id": id,
        "name": name,
        "type": type,
        "action": action,
        "severity": severity,
        "applies_to": applies_to,
        "enabled": enabled,
        "config": cfg,
    }


# ---------------------------------------------------------------------------
# block
# ---------------------------------------------------------------------------


class TestBlock:
    def test_block_sets_blocked_rule(self):
        rules = [_rule(name="block-rule", action="block", patterns=[r"\bpassword\b"])]
        out = evaluate_guardrails(rules, "my password is 1234", "input")
        assert out.blocked_rule == "block-rule"

    def test_block_records_hit(self):
        rules = [_rule(id="r1", name="block-rule", action="block", patterns=[r"\bpassword\b"])]
        out = evaluate_guardrails(rules, "my password", "input")
        assert len(out.hits) == 1
        h = out.hits[0]
        assert h["guardrail_id"] == "r1"
        assert h["action_taken"] == "block"
        assert h["input_or_output"] == "input"

    def test_block_first_match_wins(self):
        """When two block rules match, only the first fires and processing stops."""
        rules = [
            _rule(id="r1", name="first-block", action="block", patterns=[r"\bsecret\b"]),
            _rule(id="r2", name="second-block", action="block", patterns=[r"\bsecret\b"]),
        ]
        out = evaluate_guardrails(rules, "secret data", "input")
        assert out.blocked_rule == "first-block"
        assert len(out.hits) == 1  # processing stopped after first block

    def test_block_stops_further_processing(self):
        """A flag rule after a block rule must not be evaluated."""
        rules = [
            _rule(id="r1", name="block-rule", action="block", patterns=[r"\bsecret\b"]),
            _rule(id="r2", name="flag-rule", action="flag", patterns=[r"\bsecret\b"]),
        ]
        out = evaluate_guardrails(rules, "secret", "input")
        assert out.blocked_rule == "block-rule"
        assert len(out.hits) == 1  # flag rule never ran

    def test_block_text_unchanged(self):
        """Block doesn't modify text."""
        rules = [_rule(action="block", patterns=[r"\bsecret\b"])]
        original = "my secret key"
        out = evaluate_guardrails(rules, original, "input")
        assert out.text == original


# ---------------------------------------------------------------------------
# redact
# ---------------------------------------------------------------------------


class TestRedact:
    def test_redact_replaces_match(self):
        rules = [_rule(action="redact", patterns=[r"\d{4}-\d{4}-\d{4}-\d{4}"])]
        out = evaluate_guardrails(rules, "card: 1234-5678-9012-3456 ok", "input")
        assert "1234-5678-9012-3456" not in out.text
        assert "[REDACTED]" in out.text

    def test_redact_custom_mask(self):
        rules = [_rule(action="redact", patterns=[r"\bSSN\b"], mask="[SSN]")]
        out = evaluate_guardrails(rules, "my SSN is private", "input")
        assert "[SSN]" in out.text
        assert "SSN is" not in out.text

    def test_redact_all_matches(self):
        """Every occurrence of the pattern must be replaced."""
        rules = [_rule(action="redact", patterns=[r"\bsecret\b"])]
        out = evaluate_guardrails(rules, "secret and more secret stuff", "input")
        assert "secret" not in out.text
        assert out.text.count("[REDACTED]") == 2

    def test_redact_multiple_patterns(self):
        """All patterns in a single rule are applied."""
        rules = [
            _rule(
                action="redact",
                patterns=[r"\bpassword\b", r"\bsecret\b"],
            )
        ]
        out = evaluate_guardrails(rules, "password and secret here", "input")
        assert "password" not in out.text
        assert "secret" not in out.text

    def test_redact_multiple_rules(self):
        """Multiple redact rules are all applied."""
        rules = [
            _rule(id="r1", name="r1", action="redact", patterns=[r"\bpassword\b"]),
            _rule(id="r2", name="r2", action="redact", patterns=[r"\bsecret\b"]),
        ]
        out = evaluate_guardrails(rules, "password and secret", "input")
        assert "password" not in out.text
        assert "secret" not in out.text
        assert len(out.hits) == 2

    def test_redact_is_case_insensitive(self):
        rules = [_rule(action="redact", patterns=[r"\bsecret\b"])]
        out = evaluate_guardrails(rules, "SECRET data", "input")
        assert "SECRET" not in out.text

    def test_redact_blocked_rule_is_none(self):
        rules = [_rule(action="redact", patterns=[r"\bsecret\b"])]
        out = evaluate_guardrails(rules, "secret", "input")
        assert out.blocked_rule is None


# ---------------------------------------------------------------------------
# flag
# ---------------------------------------------------------------------------


class TestFlag:
    def test_flag_records_hit(self):
        rules = [_rule(id="r1", action="flag", patterns=[r"\bsecret\b"])]
        out = evaluate_guardrails(rules, "secret", "input")
        assert len(out.hits) == 1
        assert out.hits[0]["action_taken"] == "flag"

    def test_flag_text_unchanged(self):
        rules = [_rule(action="flag", patterns=[r"\bsecret\b"])]
        original = "my secret here"
        out = evaluate_guardrails(rules, original, "input")
        assert out.text == original

    def test_flag_no_blocked_rule(self):
        rules = [_rule(action="flag", patterns=[r"\bsecret\b"])]
        out = evaluate_guardrails(rules, "secret", "input")
        assert out.blocked_rule is None

    def test_unknown_action_hit_only_text_unchanged(self):
        rules = [_rule(action="log_only", patterns=[r"\bsecret\b"])]
        original = "my secret"
        out = evaluate_guardrails(rules, original, "input")
        assert out.text == original
        assert len(out.hits) == 1


# ---------------------------------------------------------------------------
# applies_to filtering
# ---------------------------------------------------------------------------


class TestAppliesTo:
    def test_input_rule_fires_on_input(self):
        rules = [_rule(applies_to="input", action="flag", patterns=[r"\bsecret\b"])]
        out = evaluate_guardrails(rules, "secret", "input")
        assert len(out.hits) == 1

    def test_input_rule_ignored_for_output(self):
        rules = [_rule(applies_to="input", action="flag", patterns=[r"\bsecret\b"])]
        out = evaluate_guardrails(rules, "secret", "output")
        assert len(out.hits) == 0

    def test_output_rule_fires_on_output(self):
        rules = [_rule(applies_to="output", action="flag", patterns=[r"\bsecret\b"])]
        out = evaluate_guardrails(rules, "secret", "output")
        assert len(out.hits) == 1

    def test_output_rule_ignored_for_input(self):
        rules = [_rule(applies_to="output", action="flag", patterns=[r"\bsecret\b"])]
        out = evaluate_guardrails(rules, "secret", "input")
        assert len(out.hits) == 0

    def test_both_rule_fires_on_input(self):
        rules = [_rule(applies_to="both", action="flag", patterns=[r"\bsecret\b"])]
        out = evaluate_guardrails(rules, "secret", "input")
        assert len(out.hits) == 1

    def test_both_rule_fires_on_output(self):
        rules = [_rule(applies_to="both", action="flag", patterns=[r"\bsecret\b"])]
        out = evaluate_guardrails(rules, "secret", "output")
        assert len(out.hits) == 1

    def test_default_applies_to_is_input(self):
        """A rule without applies_to should default to 'input'."""
        rule = {
            "id": "r1",
            "name": "r1",
            "type": "pii",
            "action": "flag",
            "severity": "high",
            "enabled": True,
            "config": {"patterns": [r"\bsecret\b"]},
            # No 'applies_to' key
        }
        out = evaluate_guardrails([rule], "secret", "input")
        assert len(out.hits) == 1
        out2 = evaluate_guardrails([rule], "secret", "output")
        assert len(out2.hits) == 0


# ---------------------------------------------------------------------------
# disabled rules
# ---------------------------------------------------------------------------


class TestDisabledRules:
    def test_disabled_rule_skipped(self):
        rules = [_rule(action="block", enabled=False, patterns=[r"\bsecret\b"])]
        out = evaluate_guardrails(rules, "secret", "input")
        assert out.blocked_rule is None
        assert len(out.hits) == 0

    def test_default_enabled_is_true(self):
        rule = {
            "id": "r1",
            "name": "r1",
            "type": "pii",
            "action": "flag",
            "severity": "high",
            "applies_to": "input",
            "config": {"patterns": [r"\bsecret\b"]},
            # No 'enabled' key — should default to True
        }
        out = evaluate_guardrails([rule], "secret", "input")
        assert len(out.hits) == 1


# ---------------------------------------------------------------------------
# bad regex — never raises
# ---------------------------------------------------------------------------


class TestBadRegex:
    def test_bad_regex_skipped_no_raise(self):
        rules = [_rule(action="block", patterns=[r"[invalid(", r"\bsecret\b"])]
        # Should not raise; bad pattern skipped; good pattern still matches
        out = evaluate_guardrails(rules, "secret", "input")
        assert out.blocked_rule is not None

    def test_all_bad_regex_no_raise_no_hit(self):
        bad_pat = "(?P<bad"
        rules = [_rule(action="block", patterns=["[invalid(", bad_pat])]
        out = evaluate_guardrails(rules, "anything", "input")
        assert out.blocked_rule is None
        assert len(out.hits) == 0


# ---------------------------------------------------------------------------
# empty rules
# ---------------------------------------------------------------------------


class TestEmptyRules:
    def test_empty_rules_unchanged_text(self):
        out = evaluate_guardrails([], "hello world", "input")
        assert out.text == "hello world"
        assert out.blocked_rule is None
        assert out.hits == []

    def test_no_matching_pattern_unchanged(self):
        rules = [_rule(action="flag", patterns=[r"\bsecret\b"])]
        original = "nothing to see here"
        out = evaluate_guardrails(rules, original, "input")
        assert out.text == original
        assert len(out.hits) == 0


# ---------------------------------------------------------------------------
# hit dict shape
# ---------------------------------------------------------------------------


class TestHitShape:
    def test_hit_fields_present(self):
        rules = [_rule(id="gid-1", type="pii", action="flag", severity="medium")]
        out = evaluate_guardrails(rules, "secret", "input")
        h = out.hits[0]
        assert "guardrail_id" in h
        assert "guardrail_type" in h
        assert "action_taken" in h
        assert "severity" in h
        assert "input_or_output" in h

    def test_hit_direction_output(self):
        rules = [_rule(applies_to="output", action="flag")]
        out = evaluate_guardrails(rules, "secret", "output")
        assert out.hits[0]["input_or_output"] == "output"
