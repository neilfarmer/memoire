"""Unit tests for lambda/assistant/facts.py."""

from conftest import load_lambda

fct = load_lambda("assistant", "facts.py")


class TestCanonicalKey:
    def test_aliases_goals_to_goal(self):
        assert fct.canonical_key("fitness_goal")  == "goal"
        assert fct.canonical_key("long_term_goal") == "goal"
        assert fct.canonical_key("goals")         == "goal"

    def test_normalizes_case_and_spaces(self):
        assert fct.canonical_key("Favorite Foods") == "favorite_food"

    def test_passthrough_unknown(self):
        assert fct.canonical_key("weirdo") == "weirdo"

    def test_handles_empty(self):
        assert fct.canonical_key("") == ""
        assert fct.canonical_key(None) == ""


class TestLooksLikeTask:
    def test_go_to_store_is_task(self):
        assert fct.looks_like_task("go to the store to pick up eggs")

    def test_finish_chapter_is_task(self):
        assert fct.looks_like_task("finish Rust book chapter 10")

    def test_durable_hobby_not_task(self):
        assert not fct.looks_like_task("running")
        assert not fct.looks_like_task("learning conversational Spanish")

    def test_numeric_fragment_is_task(self):
        # Leftover from old comma-split bug: "000 emergency fund"
        assert fct.looks_like_task("000 emergency fund")
        assert fct.looks_like_task("$5")

    def test_empty_is_task(self):
        assert fct.looks_like_task("")
        assert fct.looks_like_task("   ")


class TestListDetection:
    def test_currency_not_list(self):
        assert not fct.is_list_value("save $5,000 emergency fund")
        assert fct.split_items("save $5,000 emergency fund") == ["save $5,000 emergency fund"]

    def test_real_list_splits(self):
        assert fct.is_list_value("burgers, pad thai, pizza")
        assert fct.split_items("burgers, pad thai, pizza") == ["burgers", "pad thai", "pizza"]

    def test_single_value(self):
        assert not fct.is_list_value("software developer")
        assert fct.split_items("software developer") == ["software developer"]

    def test_empty(self):
        assert fct.split_items("") == []


class TestDedup:
    def test_drops_exact_dupes(self):
        assert fct.dedup_items(["pizza", "pizza"]) == ["pizza"]

    def test_drops_article_variants(self):
        assert fct.dedup_items(["run 5k", "run a 5k"]) == ["run 5k"]

    def test_drops_superset_and_subset(self):
        out = fct.dedup_items(["run 5k", "run 5k under 25 minutes"])
        assert len(out) == 1

    def test_preserves_distinct(self):
        out = fct.dedup_items(["burgers", "pad thai"])
        assert out == ["burgers", "pad thai"]


class TestMergeValues:
    def test_merges_and_dedups(self):
        merged = fct.merge_values("burgers", "burgers, pad thai")
        assert merged == "burgers, pad thai"

    def test_preserves_currency(self):
        merged = fct.merge_values("save $5,000 emergency fund", "")
        assert merged == "save $5,000 emergency fund"

    def test_drops_task_leakage(self):
        merged = fct.merge_values("running", "go to the store")
        assert "go to the store" not in merged
        assert "running" in merged


class TestCleanupFacts:
    def test_merges_alias_keys(self):
        facts_in = {
            "goal":          "pass AWS Solutions Architect",
            "fitness_goal":  "run 5k under 25 minutes",
            "long_term_goal": "save $5,000 emergency fund",
        }
        new, removed = fct.cleanup_facts(facts_in)
        assert "goal" in new
        assert "fitness_goal" not in new
        assert "long_term_goal" not in new
        assert "fitness_goal" in removed
        assert "long_term_goal" in removed
        for needle in ("pass AWS", "run 5k", "$5,000"):
            assert needle in new["goal"]

    def test_repairs_comma_split_corruption(self):
        facts_in = {"goal": "save £5, 000 emergency fund, pass AWS Solutions Architect"}
        new, _ = fct.cleanup_facts(facts_in)
        # "£5" and "000 emergency fund" are both task-like fragments; they drop.
        # "pass AWS Solutions Architect" survives as a real durable goal.
        assert "pass AWS Solutions Architect" in new.get("goal", "")

    def test_drops_task_leakage_from_habit(self):
        facts_in = {
            "habit": "vitamins & supplements, go to the store to pick up eggs, discover 10 new magic items, read for 30 minutes"
        }
        new, _ = fct.cleanup_facts(facts_in)
        habit = new.get("habit", "")
        assert "vitamins & supplements" in habit
        assert "read for 30 minutes" in habit
        assert "go to the store" not in habit
        assert "discover 10 new magic items" not in habit

    def test_occupation_dedupes_overlapping(self):
        facts_in = {
            "occupation": "software developer, software developer and open source contributor, open source contributor"
        }
        new, _ = fct.cleanup_facts(facts_in)
        occ = new["occupation"]
        # The super-set item should survive and the subsumed duplicates drop.
        assert occ.count("software developer") == 1

    def test_preserves_valid_list(self):
        facts_in = {"favorite_food": "burgers, pad thai"}
        new, _ = fct.cleanup_facts(facts_in)
        assert new["favorite_food"] == "burgers, pad thai"

    def test_skips_dunder_keys(self):
        facts_in = {"__master_context__": "should not appear", "interests": "coding"}
        new, _ = fct.cleanup_facts(facts_in)
        assert "__master_context__" not in new
