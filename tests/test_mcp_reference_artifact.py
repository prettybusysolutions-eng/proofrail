import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.generate_mcp_reference_artifact import verify_artifact, write_artifact


ROOT = Path(__file__).resolve().parents[1]


class MCPReferenceArtifactTests(unittest.TestCase):
    def test_committed_artifact_is_authentic_and_reproducible(self):
        self.assertTrue(verify_artifact(ROOT / "examples" / "mcp-reference-artifact"))

    def test_fresh_artifact_verifies(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "artifact"
            write_artifact(output)
            self.assertTrue(verify_artifact(output))


if __name__ == "__main__":
    unittest.main()
