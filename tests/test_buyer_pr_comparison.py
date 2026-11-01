"""Adversarial tests for buyer-run GitHub PR fact comparison; no live network."""
import csv
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from proofrail.github_pr_compare import (
    ComparisonInputError, ProviderUnavailable, compare_prs, get_pull,
    read_expectations, run_comparison, save_json_atomic,
)

REPO = "example/repo"
HEAD = "a" * 40
BASE = "main"
ROW = {"pull_number": 42, "expected_head_sha": HEAD, "expected_base_ref": BASE}


def github_pr(**overrides):
    r = {
        "number": 42, "head": {"sha": HEAD},
        "base": {"ref": BASE, "repo": {"full_name": REPO, "id": 123}},
        "state": "closed", "merged": True,
        "merged_at": "2026-10-30T12:30:05Z",
    }
    r.update(overrides)
    return r


class BytesResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, count):
        return self.data[:count]


class BuyerPRComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.csv_path = Path(self.temp.name) / "expected.csv"
        self.output = Path(self.temp.name) / "results.json"
        self.csv_path.write_text(
            "pull_number,expected_head_sha,expected_base_ref\n"
            f"42,{HEAD},main\n", encoding="utf-8",
        )

    def compare(self, response=None, *, repo_id=None):
        return compare_prs(REPO, [ROW], repository_id=repo_id,
                           fetch=lambda _r, _n: github_pr() if response is None else response)

    def test_matching_facts_do_not_establish_approval(self):
        v = self.compare()
        self.assertEqual(v["summary"], {"total": 1, "match": 1, "mismatch": 0, "unavailable": 0})
        self.assertEqual(v["results"][0]["comparison"], "match")
        self.assertFalse(v["authorization_proven"])
        self.assertFalse(v["results"][0]["authorization_proven"])
        self.assertEqual(v["results"][0]["github"]["merged_at"], "2026-10-30T12:30:05Z")

    def test_wrong_head_ref_and_repository_are_mismatches(self):
        cases = (
            (github_pr(head={"sha": "b" * 40}), "head_sha_mismatch"),
            (github_pr(base={"ref": "release", "repo": {"full_name": REPO, "id": 123}}), "base_ref_mismatch"),
            (github_pr(base={"ref": BASE, "repo": {"full_name": "evil/repo", "id": 123}}), "repository_name_mismatch"),
            (github_pr(number=43), "pr_number_mismatch"),
        )
        for data, reason in cases:
            with self.subTest(reason=reason):
                v = self.compare(data)
                self.assertEqual(v["results"][0]["comparison"], "mismatch")
                self.assertIn(reason, v["results"][0]["differences"])

    def test_repo_id_recreation_is_detected_when_pinned(self):
        v = self.compare(repo_id=999)
        self.assertEqual(v["results"][0]["differences"], ["repository_id_mismatch"])
        self.assertEqual(self.compare(repo_id=123)["summary"]["match"], 1)

    def test_unmerged_is_not_a_match(self):
        v = self.compare(github_pr(state="open", merged=False, merged_at=None))
        self.assertEqual(v["results"][0]["differences"], ["not_merged"])

    def test_contradictory_merge_state_is_unavailable(self):
        v = self.compare(github_pr(state="open", merged=True))
        self.assertEqual(v["summary"]["unavailable"], 1)

    def test_malformed_github_identifiers_fail_closed(self):
        cases = [
            github_pr(number=True),
            github_pr(head={"sha": "123"}),
            github_pr(base={"ref": "main", "repo": {"full_name": REPO, "id": True}}),
            github_pr(merged="true"),
            github_pr(merged_at="invalid"),
            github_pr(merged_at=None),
        ]
        for data in cases:
            with self.subTest(data=data):
                self.assertEqual(self.compare(data)["summary"]["unavailable"], 1)

    def test_provider_errors_are_unavailable_not_matches(self):
        v = compare_prs(REPO, [ROW], fetch=lambda *_: (_ for _ in ()).throw(ProviderUnavailable("GitHub HTTP 403")))
        self.assertEqual(v["summary"]["unavailable"], 1)
        self.assertEqual(v["results"][0]["error"], "GitHub HTTP 403")

    def test_case_only_difference_in_branch_is_rejected(self):
        self.assertEqual(self.compare(github_pr(base={"ref": "Main", "repo": {"full_name": REPO, "id": 123}}))["summary"]["mismatch"], 1)

    def test_repo_name_case_difference_is_not_recreation(self):
        self.assertEqual(self.compare(github_pr(base={"ref": "main", "repo": {"full_name": "EXAMPLE/REPO", "id": 123}}))["summary"]["match"], 1)

    def test_csv_normalization_and_bom(self):
        self.csv_path.write_bytes(("\ufeffpull_number,expected_head_sha,expected_base_ref\n"
                                   f"42,{HEAD.upper()},main\n").encode("utf-8"))
        self.assertEqual(read_expectations(self.csv_path), [ROW])

    def test_csv_wrong_headers_refused(self):
        for data in ["x,y,z\n42,x,y\n", "pull_number,expected_head_sha\n42,x\n",
                     "pull_number,expected_head_sha,expected_base_ref,payload\n42,x,y,z\n"]:
            with self.subTest(data=data):
                self.csv_path.write_text(data)
                with self.assertRaises(ComparisonInputError):
                    read_expectations(self.csv_path)

    def test_csv_duplicate_prs_refused(self):
        with self.csv_path.open("a") as f:
            f.write(f"42,{HEAD},main\n")
        with self.assertRaisesRegex(ComparisonInputError, "duplicate"):
            read_expectations(self.csv_path)

    def test_csv_bad_pr_head_and_ref_refused(self):
        for row in (f"0,{HEAD},main", f"01,{HEAD},main", "42,broken,main",
                    f"42,{HEAD},", f"42,{HEAD},main\t"):
            with self.subTest(row=row):
                self.csv_path.write_text("pull_number,expected_head_sha,expected_base_ref\n" + row + "\n")
                with self.assertRaises(ComparisonInputError):
                    read_expectations(self.csv_path)

    def test_extra_csv_fields_refused(self):
        self.csv_path.write_text(
            "pull_number,expected_head_sha,expected_base_ref\n"
            f"42,{HEAD},main,unexpected\n"
        )
        with self.assertRaises(ComparisonInputError):
            read_expectations(self.csv_path)

    def test_empty_and_oversized_input_refused(self):
        self.csv_path.write_text("pull_number,expected_head_sha,expected_base_ref\n")
        with self.assertRaises(ComparisonInputError):
            read_expectations(self.csv_path)
        self.csv_path.write_bytes(b"x" * 256001)
        with self.assertRaises(ComparisonInputError):
            read_expectations(self.csv_path)

    def test_over_100_rows_refused(self):
        with self.csv_path.open("w") as f:
            f.write("pull_number,expected_head_sha,expected_base_ref\n")
            for n in range(1, 102):
                f.write(f"{n},{HEAD},main\n")
        with self.assertRaisesRegex(ComparisonInputError, "100"):
            read_expectations(self.csv_path)

    def test_get_uses_only_get_to_exact_api_host_and_no_secret_in_url(self):
        captured = []
        def opener(req, timeout):
            captured.append((req, timeout))
            return BytesResponse(json.dumps(github_pr()).encode())
        response = get_pull(REPO, 42, token="test-secret", opener=opener)
        self.assertEqual(response["number"], 42)
        req, timeout = captured[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.full_url, "https://api.github.com/repos/example/repo/pulls/42")
        self.assertNotIn("test-secret", req.full_url)
        self.assertEqual(req.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(timeout, 15)

    def test_no_token_header_without_token(self):
        def opener(req, timeout):
            self.assertIsNone(req.get_header("Authorization"))
            return BytesResponse(json.dumps(github_pr()).encode())
        get_pull(REPO, 42, opener=opener)

    def test_default_transport_installs_redirect_refusal(self):
        from proofrail.github_pr_compare import _NoRedirect

        class FakeOpener:
            def open(self, req, timeout=15):
                return BytesResponse(json.dumps(github_pr()).encode())

        with patch("proofrail.github_pr_compare.urllib.request.build_opener",
                   return_value=FakeOpener()) as builder:
            get_pull(REPO, 42, token="buyer-token")
            self.assertEqual(len(builder.call_args.args), 1)
            redirector = builder.call_args.args[0]
            self.assertIsInstance(redirector, _NoRedirect)
            request = __import__("urllib.request", fromlist=["Request"]).Request(
                "https://api.github.com/repos/example/repo/pulls/42",
                headers={"Authorization": "Bearer buyer-token"},
            )
            self.assertIsNone(redirector.redirect_request(
                request, None, 302, "Moved", {}, "https://attacker.invalid/collect"
            ))

    def test_future_merge_and_inconsistent_unmerged_timestamp_fail_closed(self):
        for item in (
            github_pr(merged_at="2999-01-01T00:00:00Z"),
            github_pr(merged=False, state="closed", merged_at="2026-10-30T12:30:05Z"),
        ):
            with self.subTest(item=item):
                self.assertEqual(self.compare(item)["summary"]["unavailable"], 1)

    def test_malformed_and_huge_network_responses_refused(self):
        for raw in (b"[]", b"{broken", b"x" * 256001):
            with self.subTest(length=len(raw)):
                with self.assertRaises(ProviderUnavailable):
                    get_pull(REPO, 42, opener=lambda *_args, data=raw, **_kwargs: BytesResponse(data))

    def test_http_errors_do_not_leak_provider_body(self):
        def opener(*_args, **_kwargs):
            raise urllib.error.HTTPError("https://api.github.com", 403, "PRIVATE SECRET", {}, None)
        with self.assertRaisesRegex(ProviderUnavailable, "GitHub HTTP 403"):
            get_pull(REPO, 42, opener=opener)

    def test_safe_repository_name_validation(self):
        for bad in ("http://example.com/repo", "example/../../etc", "example/..",
                    "example/repo?x=1", "example/repo/other"):
            with self.subTest(bad=bad):
                with self.assertRaises(ComparisonInputError):
                    compare_prs(bad, [ROW], fetch=lambda *_: github_pr())

    def test_json_output_atomic_and_complete(self):
        data = self.compare()
        save_json_atomic(self.output, data)
        self.assertEqual(json.loads(self.output.read_text()), data)
        self.assertEqual(list(Path(self.temp.name).glob(".proofrail-*")), [])

    def test_cli_invalid_csv_does_not_call_github(self):
        self.csv_path.write_text("invalid\n")
        args = SimpleNamespace(repository=REPO, input=str(self.csv_path),
                               output=str(self.output), repository_id=None)
        with patch("proofrail.github_pr_compare.get_pull", side_effect=AssertionError("network called")):
            with patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(run_comparison(args), 2)
        self.assertFalse(self.output.exists())

    def test_cli_matching_writes_result_and_exits_zero(self):
        args = SimpleNamespace(repository=REPO, input=str(self.csv_path),
                               output=str(self.output), repository_id=123)
        with patch("proofrail.github_pr_compare.get_pull", return_value=github_pr()):
            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(run_comparison(args), 0)
        self.assertFalse(json.loads(self.output.read_text())["authorization_proven"])

    def test_cli_mismatch_exits_one_and_unavailable_exits_two(self):
        args = SimpleNamespace(repository=REPO, input=str(self.csv_path),
                               output=str(self.output), repository_id=None)
        for response, code in [(github_pr(head={"sha": "b" * 40}), 1),
                               (ProviderUnavailable("offline"), 2)]:
            with self.subTest(code=code):
                with patch("proofrail.github_pr_compare.get_pull", side_effect=response if isinstance(response, Exception) else None,
                           return_value=response if isinstance(response, dict) else None):
                    with patch("sys.stdout", new_callable=io.StringIO):
                        self.assertEqual(run_comparison(args), code)
                    self.assertEqual(json.loads(self.output.read_text())["summary"]["match"], 0)

    def test_cli_rejects_overwriting_input(self):
        args = SimpleNamespace(repository=REPO, input=str(self.csv_path),
                               output=str(self.csv_path), repository_id=None)
        with patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(run_comparison(args), 2)
        self.assertIn("pull_number", self.csv_path.read_text())


if __name__ == "__main__":
    unittest.main()
