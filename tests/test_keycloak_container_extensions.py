"""Regression checks for stopped Keycloak container inventory."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"scripts/audit_keycloak_container_extensions.py"
spec=importlib.util.spec_from_file_location("ext_audit",SCRIPT)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class ContainerExtensionsTests(unittest.TestCase):
    def test_only_explicit_paths(self):
        self.assertEqual(set(mod.TARGETS),{"providers","themes"})
        self.assertNotIn("data", " ".join(mod.TARGETS.values()))
        self.assertEqual(mod.NAME,"afyaevidence-keycloak-local")

    def test_report_contains_counts_not_names(self):
        def copy(*args,timeout=40):
            kind=args[1].split(":")[-1]
            output=Path(args[2])
            output.mkdir(parents=True,exist_ok=True)
            if "/providers/" in kind:
                (output/"very_private_provider.jar").write_bytes(b"sample")
            else:
                (output/"confidential_theme").mkdir()
                (output/"confidential_theme"/"style.css").write_text("sample")
            return ""
        with tempfile.TemporaryDirectory() as temp, patch.object(mod,"docker",side_effect=copy):
            summary=mod.inspect_filesystem(mod.NAME,Path(temp))
            self.assertEqual(summary["provider_jars"],1)
            self.assertEqual(summary["theme_directories"],1)
            self.assertEqual(summary["custom_theme_files"],1)
            self.assertNotIn("confidential",str(summary))
            self.assertNotIn("private",str(summary))

    def test_missing_folder_is_not_misreported_empty(self):
        with patch.object(mod,"docker",side_effect=RuntimeError("no_dir")):
            summary=mod.inspect_filesystem(mod.NAME,Path("."))
        self.assertEqual(summary["provider_jars"],"NOT_VERIFIED")
        self.assertEqual(summary["theme_directories"],"NOT_VERIFIED")

if __name__=="__main__":
    unittest.main()
