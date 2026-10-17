"""Regression test for /scrape Step 1 query translation (#536).

The scraper spec (SKILL.md + search-queries.md) is the implementation, so
these tests pin the invariant that broke silently: search-queries.md templates
were written in Google syntax (`site:`, `OR`, quoted phrases) and sent to
portal CLIs, which don't support `OR` or Google-style quoting. The failure was
silent — the search returned hits, just the wrong ones. The fix separates
Portal CLI search terms (plain, one per call) from WebSearch `site:` fallback
queries (labeled as Step 1c only). WebSearch honors OR, so the OR check is
scoped to CLI blocks only, and the per-portal quoting rule lives as a one-line
Query syntax note in each portal's own SKILL.md.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
QUERIES = REPO / ".claude" / "skills" / "job-scraper" / "search-queries.md"
SKILL = REPO / ".claude" / "skills" / "job-scraper" / "SKILL.md"


def _code_blocks(text: str) -> list[str]:
    """Extract contents of all fenced code blocks from markdown."""
    return re.findall(r"```(?:markdown)?\n(.*?)```", text, re.DOTALL)


def _steps(text: str) -> dict[str, str]:
    """Split the skill spec into {heading: body} by '###' step headers."""
    result = {}
    for part in text.split("\n### ")[1:]:
        heading, _, body = part.partition("\n")
        result[heading.strip()] = body
    return result


class TestNoGoogleOperatorsInTemplates(unittest.TestCase):
    """No portal CLI supports OR; only WebSearch fallback blocks may use it (#536).

    WebSearch honors OR, so the check is scoped to the Portal CLI search term
    blocks (code blocks without a `site:` prefix) — the fallback blocks are
    allowed to combine site targets with OR.
    """

    def test_no_OR_in_portal_cli_search_term_blocks(self):
        """Portal CLI search term blocks must avoid ` OR `."""
        text = QUERIES.read_text(encoding="utf-8")
        blocks = _code_blocks(text)
        self.assertGreaterEqual(len(blocks), 1, "no code blocks found in search-queries.md")
        cli_blocks = [b for b in blocks if "site:" not in b]
        self.assertGreaterEqual(
            len(cli_blocks), 4,
            "search-queries.md must have at least 4 Portal CLI search term blocks "
            "(one per priority category) without site: prefixes",
        )
        for block in cli_blocks:
            for line in block.strip().splitlines():
                # `OR` as a standalone word between terms is the bug from #536.
                # Portal CLI search term blocks are the only content checked —
                # any OR there is a portal-incompatible operator.
                self.assertNotRegex(
                    line, r"\bOR\b",
                    f"search-queries.md must not send OR to portal CLIs: {line!r}",
                )


class TestSearchQueriesSeparateCliAndWebSearch(unittest.TestCase):
    """site: queries must be WebSearch fallback only; CLI terms must be plain."""
    def test_has_portal_cli_search_terms_sections(self):
        """Each priority section must list plain CLI search terms per call."""
        text = QUERIES.read_text(encoding="utf-8")
        self.assertIn(
            "Portal CLI search terms", text,
            "search-queries.md must list Portal CLI search terms separately "
            "from site: WebSearch fallback queries",
        )

    def test_site_queries_are_labeled_step1c_only(self):
        """site: query blocks must be introduced as WebSearch fallback only."""
        text = QUERIES.read_text(encoding="utf-8")
        self.assertIn(
            "WebSearch fallback queries", text,
            "search-queries.md must label site: query blocks as WebSearch fallback",
        )
        self.assertIn(
            "Step 1c only", text,
            "search-queries.md must label site: queries as Step 1c only, not CLI input",
        )

    def test_cli_search_term_blocks_have_no_site_prefix(self):
        """Portal CLI search term blocks must not contain site: prefixes."""
        text = QUERIES.read_text(encoding="utf-8")
        blocks = _code_blocks(text)
        cli_blocks = [b for b in blocks if "site:" not in b]
        self.assertGreaterEqual(
            len(cli_blocks), 4,
            "search-queries.md must have at least 4 Portal CLI search term blocks "
            "(one per priority category) without site: prefixes",
        )


class TestCliSearchTermsArePlainUnquoted(unittest.TestCase):
    """Portal CLI search term blocks must carry plain (unquoted) terms (#536).

    Quoting is a per-portal concern documented in each portal's SKILL.md
    Query syntax note — the template itself must not pre-quote terms, because
    that misleads scrapers into sending literal quote characters to portals
    that don't honor them (the Priority 1/2 blocks shipped quoted and duplicated).
    """

    def test_cli_search_term_blocks_have_no_quoted_terms(self):
        """No line in a CLI search term block may be a fully quoted phrase."""
        text = QUERIES.read_text(encoding="utf-8")
        blocks = _code_blocks(text)
        cli_blocks = [b for b in blocks if "site:" not in b]
        self.assertGreaterEqual(len(cli_blocks), 4, "need at least 4 CLI term blocks")
        for block in cli_blocks:
            for line in block.strip().splitlines():
                stripped = line.strip()
                self.assertFalse(
                    stripped.startswith('"') and stripped.endswith('"'),
                    f"Portal CLI search term must not be wrapped in quotes: {line!r}",
                )

    def test_no_duplicate_lines_in_cli_search_term_blocks(self):
        """No CLI search term block may repeat the same term twice."""
        text = QUERIES.read_text(encoding="utf-8")
        blocks = _code_blocks(text)
        cli_blocks = [b for b in blocks if "site:" not in b]
        self.assertGreaterEqual(len(cli_blocks), 4, "need at least 4 CLI term blocks")
        for i, block in enumerate(cli_blocks):
            lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
            seen = set()
            for line in lines:
                self.assertNotIn(
                    line, seen,
                    f"Duplicate CLI search term in block {i}: {line!r}",
                )
                seen.add(line)


class TestSkill1bDocumentsQuotingRules(unittest.TestCase):
    """Step 1b must point each portal to its own SKILL.md Query syntax note,
    not hardcode a per-portal quoting list (#536)."""

    @classmethod
    def setUpClass(cls):
        text = SKILL.read_text(encoding="utf-8")
        steps = _steps(text)
        cls.step1 = steps.get("Step 1: Search", "")
        cls.step1b = cls.step1.partition("#### 1b.")[2]

    def test_step1b_instructs_one_term_per_call(self):
        """Step 1b must say one plain term per CLI call, no OR, no combined strings."""
        lower = self.step1b.lower()
        self.assertTrue(
            "one plain term" in lower or "one term per call" in lower,
            "Step 1b must instruct one plain term per CLI call (no OR, no combined strings)",
        )

    def test_step1b_references_portal_skill_docs_for_quoting(self):
        """Step 1b must point each portal to its own SKILL.md for the quoting rule,
        not hardcode a portal list."""
        lower = self.step1b.lower()
        self.assertIn(
            "quot", lower,
            "Step 1b must mention quoting and point each portal's SKILL.md",
        )
        self.assertIn(
            "query syntax", lower,
            "Step 1b must reference each portal's SKILL.md Query syntax note",
        )
        # The quoting rule must not hardcode portal names — it references each
        # portal's own SKILL.md instead.
        self.assertNotIn(
            "quote multi-word terms on", lower,
            "Step 1b must not hardcode a portal quoting list — each portal's "
            "SKILL.md carries the rule instead",
        )


class TestSkill1bDoesNotMatchSiteTarget(unittest.TestCase):
    """Step 1b must not match `site:` targets to decide which CLI to invoke (#536).

    The discovery rule is portal-CLI-first: /scrape runs every installed portal
    CLI, and WebSearch fallbacks only for portals without a CLI. Matching a
    `site:` target to pick a CLI contradicts that discovery rule and the
    intro's "you do not need a matching `site:` line" guarantee.
    """

    def test_step1b_has_no_site_target_matching(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertNotIn(
            "Match the `site:` target", text,
            "Step 1b must not match site: targets to decide which CLI to invoke",
        )


class TestSkill1cHonorsOr(unittest.TestCase):
    """Step 1c must state that WebSearch honors OR (#536)."""

    @classmethod
    def setUpClass(cls):
        text = SKILL.read_text(encoding="utf-8")
        steps = _steps(text)
        cls.step1 = steps.get("Step 1: Search", "")
        cls.step1c = cls.step1.partition("#### 1c.")[2]

    def test_step1c_says_websearch_honors_or(self):
        lower = self.step1c.lower()
        self.assertIn(
            "honors", lower,
            "Step 1c must state that WebSearch honors OR",
        )
        self.assertNotIn(
            "not documented to honor", lower,
            "Step 1c must not claim WebSearch does not honor OR",
        )


class TestSkill1cLabelsSiteQueriesAsFallbackOnly(unittest.TestCase):
    """Step 1c must use the labeled WebSearch site: blocks, not raw template lines."""

    @classmethod
    def setUpClass(cls):
        text = SKILL.read_text(encoding="utf-8")
        steps = _steps(text)
        cls.step1 = steps.get("Step 1: Search", "")
        cls.step1c = cls.step1.partition("#### 1c.")[2]

    def test_step1c_references_labeled_fallback_blocks(self):
        """Step 1c must point at the 'WebSearch fallback query' blocks, not generic strings."""
        self.assertIn(
            "WebSearch fallback query", self.step1c,
            "Step 1c must reference the labeled WebSearch fallback query blocks from search-queries.md",
        )
        self.assertIn(
            "Step 1c only", self.step1c,
            "Step 1c must reference the Step 1c-only-labeled site: queries",
        )


if __name__ == "__main__":
    unittest.main()