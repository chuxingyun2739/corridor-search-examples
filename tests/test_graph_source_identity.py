"""Frozen source/input identities; these checks execute no graph benchmark."""
import ast
import hashlib
import json
from pathlib import Path
import unittest

REPO = Path(__file__).absolute().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


class SourceIdentityTests(unittest.TestCase):
    def test_source_hashes_and_byte_preservation(self):
        manifest = json.loads((REPO / "configs/graph/runtime_sources.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["archive_sha256"])
        for item in manifest["files"]:
            with self.subTest(path=item["public_path"]):
                self.assertEqual(sha((REPO / item["public_path"]).read_bytes()), item["after_sha256"])
                if item["transformation"] == "BYTE_IDENTICAL":
                    self.assertEqual(item["before_sha256"], item["after_sha256"])

    def test_extracted_algorithm_bodies_equal_archived_ast_hashes(self):
        manifest = json.loads((REPO / "configs/graph/runtime_sources.json").read_text(encoding="utf-8"))
        for item in manifest["algorithm_bodies"]:
            tree = ast.parse((REPO / item["public_path"]).read_text(encoding="utf-8-sig"))
            names = set(item["top_level_names"])
            bodies = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
            self.assertEqual(len(bodies), len(names))
            representation = "\n".join(ast.dump(node, include_attributes=False) for node in bodies)
            self.assertEqual(sha(representation.encode()), item["archived_ast_sha256"], item["public_path"])

    def test_all_authored_input_hashes_and_oracle_bindings(self):
        manifest = json.loads((REPO / "benchmarks/graph/frozen_inputs.json").read_text(encoding="utf-8"))
        entries = {row["case"]: row for row in manifest["inputs"]}
        small = [row for row in entries.values() if row["provenance"] == "frozen_227_authored_small_graphs"]
        self.assertEqual(len(small), 227)
        for entry in entries.values():
            data = (REPO / entry["path"]).read_bytes()
            self.assertEqual(sha(data), entry["sha256"], entry["case"])
            parsed = json.loads(data)
            self.assertEqual(parsed["case"], entry["case"])
            if entry in small:
                self.assertEqual(parsed["network_type"], "synthetic_exact_validation")
        oracle = json.loads((REPO / "benchmarks/graph/oracle_227.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(len(oracle), 227)
        for row in oracle:
            self.assertEqual(row["input_sha256"], entries[row["case"]]["sha256"])


if __name__ == "__main__":
    unittest.main()
