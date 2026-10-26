"""Offline briefcase tests: no network, no review submission, no unsafe HTML."""
import importlib.util
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"scripts/export_offline_briefcase.py"
SPEC=importlib.util.spec_from_file_location("briefcase",SCRIPT)
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

def receipt():
    return {
        "schema_version":"agent-run-1",
        "execution_status":"ready_for_review",
        "review_status":"awaiting_human_review",
        "data_mode":"fixture","model_mode":"scripted",
        "memory_mode":"disabled_fixture",
        "candidate_brief":{
            "review_status":"awaiting_human_review","semantic_review_required":True,
            "approval":None,"summary":"Synthetic increase <script>alert(1)</script>",
            "explanation":"insufficient_data",
            "numerical_statements":[{"metric_ref":"mt_1","text":"comparison / all_available / canonical: positive_total = 100 count","evidence_ids":["ev_a"]}],
            "evidence_ids":["ev_a"],
            "limitations":["synthetic_data","no_causal_attribution"],
            "next_checks":["human_review"]},
        "evidence_bundle":{"data_mode":"fixture","snapshot_id":"ss_"+"a"*64,
                           "evidence_records":[{"evidence_id":"ev_a","record":{"private":"secret"}}],
                           "metrics":[{"metric_ref":"mt_1","period":"comparison",
                           "cohort":"all_available","view":"canonical","name":"positive_total",
                           "value":100,"unit":"count","evidence_ids":["ev_a"]}]}
    }

class OfflineBriefcaseTests(unittest.TestCase):
    def test_html_is_offline_and_escaped(self):
        html=MOD.render(receipt(),"b"*64)
        self.assertIn("Content-Security-Policy",html)
        self.assertNotIn("<script>alert(1)</script>",html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;",html)
        self.assertIn("READ-ONLY",html)
        self.assertIn("AWAITING HUMAN REVIEW",html)
        self.assertNotIn("secret",html)
        self.assertNotIn("<form",html.lower())
        self.assertNotIn("<script",html.lower().replace("&lt;script",""))
        self.assertNotIn("https://",html.lower())

    def test_rejects_live_modes_and_approval(self):
        doc=receipt()
        for field,value in (("data_mode","zetaris"),("model_mode","ollama"),("memory_mode","hmem_reference")):
            altered=receipt()
            altered[field]=value
            with self.assertRaises(ValueError):
                MOD.render(altered,"c"*64)
        doc["candidate_brief"]["approval"]="accept"
        with self.assertRaises(ValueError):
            MOD.render(doc,"c"*64)

    def test_numerical_statement_tampering_is_rejected(self):
        doc=receipt()
        doc["candidate_brief"]["numerical_statements"][0]["text"] = (
            "comparison / all_available / canonical: positive_total = 999 count")
        with self.assertRaises(ValueError):
            MOD.render(doc,"c"*64)

    def test_missing_or_fabricated_evidence_id_rejected(self):
        doc=receipt()
        doc["candidate_brief"]["evidence_ids"]=["unverified"]
        with self.assertRaises(ValueError):
            MOD.render(doc,"c"*64)

    def test_file_written_once_and_receipt_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            source=folder/"receipt.json"
            source.write_text(json.dumps(receipt()),encoding="utf-8")
            destination=folder/"offline.html"
            args=[sys.executable,str(SCRIPT),"--receipt",str(source),
                  "--output",str(destination)]
            first=subprocess.run(args,capture_output=True,text=True,timeout=15)
            self.assertEqual(first.returncode,0,first.stdout+first.stderr)
            self.assertIn("OFFLINE_BRIEFCASE=PASS",first.stdout)
            self.assertTrue(destination.exists())
            before=destination.read_bytes()
            second=subprocess.run(args,capture_output=True,text=True,timeout=15)
            self.assertEqual(second.returncode,2)
            self.assertEqual(before,destination.read_bytes())
            self.assertEqual(json.loads(source.read_text()),receipt())

    def test_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            source=folder/"receipt.json"
            source.write_text('{"schema_version":"agent-run-1","schema_version":"other"}',encoding="utf-8")
            dest=folder/"off.html"
            r=subprocess.run([sys.executable,str(SCRIPT),"--receipt",str(source),
                             "--output",str(dest)],capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,2)
            self.assertFalse(dest.exists())

if __name__=="__main__":
    unittest.main()
