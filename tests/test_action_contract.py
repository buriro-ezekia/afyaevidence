"""Finite action menus and fake HTTP integration; no actual model inference."""
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
from afyaevidence.agent import BRIEF_SCHEMA, ToolSession, run_agent, turn_contract
from afyaevidence.analysis import Request, investigate
from afyaevidence.model import OllamaProvider
from afyaevidence.snapshot import FixtureGateway


def variants(schema):
    return schema.get('oneOf', [schema])


def exact_tools(schema):
    """Decode the literal tool actions advertised in a request schema."""
    result = []
    for branch in variants(schema):
        fields = branch['properties']
        if fields['type'].get('const') == 'tool_call':
            result.append(dict(type='tool_call', tool=fields['tool']['const'],
                               arguments={key: value['const'] for key, value in
                                          fields['arguments']['properties'].items()}))
    return result


class ActionContractTests(unittest.TestCase):
    def session(self, dataset='fx_32e8b610', cutoff='2026-01-15T00:00:00Z'):
        source = FixtureGateway().collect(ROOT / 'data/synthetic' / dataset)
        return ToolSession(investigate(source, Request(as_of_utc=cutoff)))

    def contract(self, session, completed=(), optional=0, remaining=4):
        return turn_contract(session, list(completed), optional=optional,
                             remaining=remaining, tool_remaining=8)

    def completed(self, action):
        return dict(tool=action['tool'], arguments=action['arguments'])

    def raw(self):
        return dict(type='tool_call', tool='compare_monthly_indicators',
                    arguments=dict(view='raw_diagnostic'))

    def test_initial_choices_exclude_mandatory_calls_and_cannot_propose_a_brief(self):
        contract = self.contract(self.session())
        actions = exact_tools(contract['schema'])
        self.assertEqual(actions, contract['actions'])
        self.assertFalse(contract['allow_brief'])
        self.assertIn(self.raw(), actions)
        self.assertIn('compare_matched_facilities', {a['tool'] for a in actions})
        self.assertIn('get_evidence_records', {a['tool'] for a in actions})
        self.assertNotIn('get_reporting_quality', {a['tool'] for a in actions})
        self.assertNotIn('recall_review_context', {a['tool'] for a in actions})
        self.assertTrue(all(a['arguments'].get('view') != 'canonical' for a in actions))

    def test_completed_followups_and_both_matched_variants_disappear(self):
        session = self.session()
        initial = self.contract(session)['actions']
        evidence = next(a for a in initial if a['tool'] == 'get_evidence_records')
        matched = next(a for a in initial if a['tool'] == 'compare_matched_facilities')
        done = [self.completed(a) for a in (self.raw(), evidence, matched)]
        contract = self.contract(session, done, optional=3, remaining=2)
        self.assertNotIn(self.raw(), contract['actions'])
        self.assertNotIn(evidence, contract['actions'])
        self.assertNotIn('compare_matched_facilities', {a['tool'] for a in contract['actions']})

    def test_other_followup_reserves_next_action_for_raw_facts(self):
        session = self.session()
        matched = next(a for a in self.contract(session)['actions']
                       if a['tool'] == 'compare_matched_facilities')
        contract = self.contract(session, [self.completed(matched)], optional=1, remaining=3)
        self.assertEqual([self.raw()], exact_tools(contract['schema']))
        self.assertFalse(contract['allow_brief'])

    def test_last_call_is_brief_only_after_prerequisites(self):
        contract = self.contract(self.session(), [self.completed(self.raw())], optional=1, remaining=1)
        self.assertEqual([], contract['actions'])
        self.assertTrue(contract['allow_brief'])
        self.assertEqual('brief', contract['phase'])
        self.assertEqual('propose_brief', contract['schema']['properties']['type']['const'])

    def test_evidence_batches_cover_scoped_registry_once_and_exclude_future_versions(self):
        session = self.session('fx_a061c452', '2025-12-10T00:00:00Z')
        actions = exact_tools(self.contract(session)['schema'])
        batches = [a['arguments']['evidence_ids'] for a in actions if a['tool'] == 'get_evidence_records']
        self.assertTrue(batches)
        self.assertTrue(all(1 <= len(batch) <= 20 for batch in batches))
        aliases = [alias for batch in batches for alias in batch]
        self.assertEqual(set(session.evidence), set(aliases))
        self.assertEqual({1}, set(Counter(aliases).values()))
        self.assertFalse(any(e['record'].get('report_version') == 2 for e in session.evidence.values()))
        for alias in aliases:
            record = session.evidence[alias]['record']
            self.assertNotEqual(2, record.get('report_version'))

    def test_brief_reference_enums_are_shown_only_and_empty_context_is_bounded(self):
        session = self.session()
        original = json.dumps(BRIEF_SCHEMA, sort_keys=True)
        session.call('get_reporting_quality', {})
        session.call('compare_monthly_indicators', {'view': 'canonical'})
        session.call('compare_monthly_indicators', {'view': 'raw_diagnostic'})
        contract = self.contract(session, [self.completed(self.raw())], optional=1, remaining=1)
        fields = contract['schema']['properties']
        self.assertEqual(set(session.shown_metrics), set(fields['metric_refs']['items']['enum']))
        self.assertEqual(set(session.shown_evidence), set(fields['evidence_ids']['items']['enum']))
        self.assertEqual(0, fields['review_context_ids']['maxItems'])
        self.assertNotIn('enum', fields['review_context_ids']['items'])
        self.assertEqual(original, json.dumps(BRIEF_SCHEMA, sort_keys=True))

    def test_provider_ignoring_menu_cannot_request_arbitrary_evidence_subsets(self):
        class IgnoresSchema:
            mode = 'scripted'
            model = 'malicious-contract-test'
            def next_action(self, messages, *, timeout, action_schema=None):
                baseline = json.loads(messages[1]['content'])
                alias = baseline['reporting_quality']['source_index'][0]['ref']
                return dict(content=json.dumps(dict(type='tool_call', tool='get_evidence_records',
                                                    arguments=dict(evidence_ids=[alias]))))
        result = run_agent(self.session().bundle, IgnoresSchema())
        self.assertEqual('action_not_available', result['failure_reason'])
        self.assertEqual(2, result['model_calls'])
        self.assertEqual(2, result['tool_calls'])
        self.assertIsNone(result['candidate_brief'])

    def test_fake_http_ollama_observes_state_schema_and_produces_review_only_brief(self):
        """Exercise transport and host validation; this is not a model quality test."""
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append(request)
                choices = exact_tools(request['format'])
                baseline = json.loads(request['messages'][1]['content'])
                if len(requests) == 1:
                    action = next(a for a in choices if a['tool'] == 'compare_matched_facilities')
                elif len(requests) == 2:
                    action = next(a for a in choices if a['tool'] == 'compare_monthly_indicators')
                else:
                    action = dict(type='propose_brief', explanation='reporting_artefact_supported',
                                  metric_refs=baseline['brief_requirements']['reporting_artefact_supported'],
                                  evidence_ids=[item['ref'] for item in baseline['reporting_quality']['source_index']],
                                  review_context_ids=[], limitations=['synthetic_data', 'no_causal_attribution'],
                                  next_checks=['review_source_versions', 'human_review'])
                payload = json.dumps(dict(model=request['model'], done=True,
                                          message=dict(content=json.dumps(action)))).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(payload)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = OllamaProvider(endpoint='http://127.0.0.1:' + str(server.server_port),
                                      model='fake-transport-only')
            result = run_agent(self.session().bundle, provider)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertEqual('ready_for_review', result['execution_status'], result['failure_reason'])
        self.assertEqual(3, result['model_calls'])
        self.assertEqual('awaiting_human_review', result['review_status'])
        self.assertIsNone(result['candidate_brief']['approval'])
        self.assertTrue(result['candidate_brief']['semantic_review_required'])
        self.assertEqual([self.raw()], exact_tools(requests[1]['format']))
        self.assertTrue(all('CURRENT_ACTION_SCHEMA=' in r['messages'][-1]['content'] for r in requests))
        for request in requests:
            choices = exact_tools(request['format'])
            self.assertFalse(any(a['arguments'].get('view') == 'canonical' for a in choices))


if __name__ == '__main__':
    unittest.main()
