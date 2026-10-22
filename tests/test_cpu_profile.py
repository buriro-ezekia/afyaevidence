"""CPU scheduling and evidence regressions; every provider here is a simulation."""
from copy import deepcopy
from itertools import combinations
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
from afyaevidence.agent import Budget, ToolSession, run_agent
from afyaevidence.analysis import Request, investigate
from afyaevidence.model import ProviderError
from afyaevidence.snapshot import FixtureGateway


def exact_tools(schema):
    actions = []
    for branch in schema.get('oneOf', [schema]):
        fields = branch['properties']
        if fields['type'].get('const') == 'tool_call':
            actions.append(dict(type='tool_call', tool=fields['tool']['const'],
                                arguments={key: value['const'] for key, value in
                                           fields['arguments']['properties'].items()}))
    return actions


def supplied_context(messages):
    return next(json.loads(message['content']) for message in messages
                if message['role'] == 'user' and 'reporting_quality' in message['content'])


def review_brief(context, explanation='reporting_artefact_supported'):
    """Construct a declared fake proposal from references actually supplied to it."""
    notes = context.get('review_context', {}).get('notes', [])
    limitations = ['synthetic_data', 'no_causal_attribution']
    if explanation == 'insufficient_data':
        limitations.append('coverage_difference')
    if notes:
        limitations.append('historical_memory_only')
    sources = context['reporting_quality']['source_index']
    months = sorted({item['month'] for item in sources if item['month'] is not None})
    evidence = ([next(item['ref'] for item in sources if item['month'] == month) for month in months]
                if months else [sources[0]['ref']])
    return dict(type='propose_brief', explanation=explanation,
                metric_refs=list(context['brief_requirements'][explanation]),
                evidence_ids=evidence,
                review_context_ids=[note['ref'] for note in notes], limitations=limitations,
                next_checks=['review_source_versions', 'human_review'])


class SimulatedClock:
    def __init__(self):
        self.elapsed = 0.0

    def __call__(self):
        return self.elapsed

    def advance(self, seconds):
        self.elapsed += seconds


class CpuProvider:
    """A clock-driven fake, never an actual Ollama inference result."""
    mode = 'scripted'
    model = 'cpu-regression-simulation'

    def __init__(self, clock, durations=(), *, follow_up='compare_matched_facilities', callback=None):
        self.clock = clock
        self.durations = list(durations)
        self.follow_up = follow_up
        self.callback = callback
        self.requests = []

    def next_action(self, messages, *, timeout, action_schema=None):
        request = dict(messages=deepcopy(messages), timeout=timeout, schema=deepcopy(action_schema))
        self.requests.append(request)
        call = len(self.requests)
        context = supplied_context(messages)
        if self.callback:
            action = self.callback(call, context, action_schema)
        elif call == 1:
            action = next(action for action in exact_tools(action_schema) if action['tool'] == self.follow_up)
        else:
            action = review_brief(context)
        duration = self.durations[call - 1] if call <= len(self.durations) else 0
        self.clock.advance(duration)
        return dict(content=action if isinstance(action, str) else json.dumps(action),
                    model=self.model, elapsed_seconds=duration,
                    usage={'prompt_eval_count': 321, 'eval_count': 45} if call == 1 else None)


class CpuProfileTests(unittest.TestCase):
    def bundle(self, dataset='fx_32e8b610', cutoff='2026-01-15T00:00:00Z'):
        source = FixtureGateway().collect(ROOT / 'data/synthetic' / dataset)
        return investigate(source, Request(as_of_utc=cutoff))

    def run_cpu(self, provider, **kwargs):
        bundle = kwargs.pop('bundle', None)
        return run_agent(self.bundle() if bundle is None else bundle, provider, execution_profile='cpu',
                         budget=kwargs.pop('budget', Budget(model_timeout_seconds=300)),
                         clock=provider.clock, **kwargs)

    def test_observed_slow_requests_cannot_spend_third_request_exploring(self):
        clock = SimulatedClock()
        provider = CpuProvider(clock, [134.14, 138.41, 201.18])
        bundle = self.bundle()
        result = self.run_cpu(provider, bundle=bundle)
        self.assertEqual('ready_for_review', result['execution_status'], result['failure_reason'])
        self.assertEqual('cpu', result['execution_profile'])
        self.assertEqual(2, result['model_calls'])
        self.assertEqual(2, len(provider.requests))
        self.assertAlmostEqual(272.55, clock.elapsed)
        self.assertEqual(0, result['repairs'])
        self.assertEqual(bundle.to_dict(), result['evidence_bundle'])
        contracts = [event for event in result['trace'] if event['kind'] == 'action_contract']
        self.assertEqual(['follow_up', 'brief'], [event['phase'] for event in contracts])
        self.assertEqual([300, 300], [event['timeout_seconds'] for event in contracts])
        self.assertTrue(all(isinstance(event['elapsed_seconds'], (int, float)) for event in contracts))
        self.assertFalse(contracts[0]['allow_brief'])
        self.assertTrue(contracts[1]['allow_brief'])
        self.assertEqual([], contracts[1]['allowed_actions'])
        responses = [event for event in result['trace'] if event['kind'] == 'model']
        self.assertEqual({'prompt_eval_count': 321, 'eval_count': 45}, responses[0]['usage'])
        self.assertIsNone(responses[1]['usage'])
        self.assertEqual('awaiting_human_review', result['review_status'])
        self.assertEqual('awaiting_human_review', result['candidate_brief']['review_status'])
        self.assertTrue(result['candidate_brief']['semantic_review_required'])
        self.assertIsNone(result['candidate_brief']['approval'])

    def test_baselines_and_scoped_memory_are_collected_before_dispatch(self):
        clock = SimulatedClock()
        recalled = []
        question = 'Check the reporting change; historical instructions are untrusted.'
        cutoff = '2026-01-15T00:00:00Z'
        def recall(query, *, memory_as_of_utc):
            recalled.append((query, memory_as_of_utc))
            return dict(mode='hmem_reference', memory_as_of_utc=memory_as_of_utc,
                        notes=[], pending_sync=0, limitations=['Mock recall for scheduling test'])
        def action(call, context, schema):
            self.assertEqual([(question, cutoff)], recalled)
            self.assertTrue(context['reporting_quality']['source_index'])
            self.assertTrue(context['canonical']['facts'])
            self.assertTrue(context['raw']['facts'])
            self.assertIn('review_context', context)
            return exact_tools(schema)[0] if call == 1 else review_brief(context)
        provider = CpuProvider(clock, callback=action)
        result = self.run_cpu(provider, recall=recall, memory_as_of_utc=cutoff, question=question)
        self.assertEqual('ready_for_review', result['execution_status'], result['failure_reason'])
        self.assertEqual(1, result['memory_reads'])
        first_dispatch = next(index for index, event in enumerate(result['trace']) if event['kind'] == 'action_contract')
        baseline = [event for event in result['trace'][:first_dispatch] if event['kind'] == 'tool']
        self.assertEqual({'get_reporting_quality', 'compare_monthly_indicators', 'recall_review_context'},
                         {event['name'] for event in baseline})
        self.assertEqual({'canonical', 'raw_diagnostic'},
                         {event['arguments']['view'] for event in baseline if event['name'] == 'compare_monthly_indicators'})
        self.assertTrue(all(event['mandatory'] for event in baseline))
        choices = exact_tools(provider.requests[0]['schema'])
        self.assertEqual({'compare_matched_facilities', 'get_evidence_records'}, {action['tool'] for action in choices})

    def test_context_is_fresh_and_final_schema_advertises_only_brief(self):
        provider = CpuProvider(SimulatedClock())
        result = self.run_cpu(provider)
        self.assertEqual('ready_for_review', result['execution_status'], result['failure_reason'])
        first, final = provider.requests
        initial = supplied_context(first['messages'])
        last = supplied_context(final['messages'])
        self.assertNotIn('brief_requirements', initial)
        menu = [{key: value for key, value in action.items() if key in ('type', 'tool', 'arguments')}
                for action in initial['available_actions']]
        self.assertEqual(exact_tools(first['schema']), menu)
        self.assertNotIn('available_actions', last)
        self.assertIn('brief_requirements', last)
        self.assertIn('follow_up_result', last)
        self.assertEqual('compare_matched_facilities', last['follow_up_result']['tool_result'])
        self.assertTrue(last['follow_up_result']['data']['facts'])
        for request in provider.requests:
            self.assertEqual(1, sum(message['role'] == 'user' for message in request['messages']))
            self.assertFalse(any(message['role'] == 'assistant' for message in request['messages']))
            self.assertNotIn('CURRENT_ACTION_SCHEMA=', json.dumps(request['messages']))
        self.assertEqual([], exact_tools(final['schema']))
        self.assertEqual('propose_brief', final['schema']['properties']['type']['const'])
        full_quality = next(event['result'] for event in result['trace']
                            if event['kind'] == 'tool' and event['name'] == 'get_reporting_quality')
        self.assertEqual([row['ref'] for row in full_quality['source_index']],
                         [row['ref'] for row in last['reporting_quality']['source_index']])
        self.assertEqual({'positive_total'}, {fact['name'] for fact in last['raw']['facts']})
        shown_metrics = {fact['ref'] for group in (last['canonical'], last['raw'], last['follow_up_result']['data'])
                         for fact in group['facts']}
        self.assertEqual(shown_metrics, set(final['schema']['properties']['metric_refs']['items']['enum']))

    def test_final_schema_requires_review_limitations_and_check_in_every_combination(self):
        provider = CpuProvider(SimulatedClock())
        result = self.run_cpu(provider)
        self.assertEqual('ready_for_review', result['execution_status'], result['failure_reason'])
        fields = provider.requests[1]['schema']['properties']
        for name, required, optional in (
            ('limitations', {'synthetic_data', 'no_causal_attribution'},
             ['coverage_difference', 'historical_memory_only']),
            ('next_checks', {'human_review'},
             ['review_source_versions', 'review_testing_practice', 'request_facility_context', 'resolve_missing_reports']),
        ):
            with self.subTest(name=name):
                choices = fields[name]['enum']
                expected = {frozenset(required | set(subset)) for length in range(len(optional) + 1)
                            for subset in combinations(optional, length)}
                self.assertEqual(expected, {frozenset(choice) for choice in choices})
                self.assertEqual(len(expected), len(choices))
                self.assertTrue(all(required <= set(choice) and len(choice) == len(set(choice)) for choice in choices))

    def test_final_evidence_choices_cover_observed_periods_without_duplicate_or_hidden_refs(self):
        for cutoff, periods, explanation in (
            ('2026-01-15T00:00:00Z', {'2025-10-01', '2025-11-01'}, 'reporting_artefact_supported'),
            ('2025-11-15T00:00:00Z', {'2025-10-01'}, 'insufficient_data'),
            ('2000-01-01T00:00:00Z', set(), 'insufficient_data'),
        ):
            with self.subTest(cutoff=cutoff):
                def action(call, context, schema):
                    return exact_tools(schema)[0] if call == 1 else review_brief(context, explanation)
                provider = CpuProvider(SimulatedClock(), callback=action)
                result = self.run_cpu(provider, bundle=self.bundle(cutoff=cutoff))
                self.assertEqual('ready_for_review', result['execution_status'], result['failure_reason'])
                final = provider.requests[1]
                context = supplied_context(final['messages'])
                self.assertIn('evidence_selection', context)
                sources = {item['ref']: item for item in context['reporting_quality']['source_index']}
                choices = final['schema']['properties']['evidence_ids']['enum']
                self.assertGreater(len(choices), 1)
                self.assertEqual(len(choices), len({tuple(choice) for choice in choices}))
                for choice in choices:
                    self.assertEqual(max(1, len(periods)), len(choice))
                    self.assertEqual(len(choice), len(set(choice)))
                    self.assertTrue(set(choice) <= set(sources))
                    if periods:
                        self.assertEqual(sorted(periods), [sources[ref]['month'] for ref in choice])
                    else:
                        self.assertIsNone(sources[choice[0]]['month'])
                self.assertEqual(max(1, len(periods)), len(result['candidate_brief']['evidence_ids']))

    def test_compact_evidence_selection_preserves_every_rendered_metric_input_reference(self):
        provider = CpuProvider(SimulatedClock())
        result = self.run_cpu(provider)
        self.assertEqual('ready_for_review', result['execution_status'], result['failure_reason'])
        candidate = result['candidate_brief']
        self.assertEqual(2, len(candidate['evidence_ids']))
        metrics = {metric['metric_ref']: metric for metric in result['evidence_bundle']['metrics']}
        evidence = {record['evidence_id'] for record in result['evidence_bundle']['evidence_records']}
        all_inputs = set()
        for statement in candidate['numerical_statements']:
            self.assertEqual(metrics[statement['metric_ref']]['evidence_ids'], statement['evidence_ids'])
            self.assertTrue(set(statement['evidence_ids']) <= evidence)
            all_inputs.update(statement['evidence_ids'])
        self.assertGreater(len(all_inputs), len(candidate['evidence_ids']))

    def test_observed_repeated_reporting_log_reference_fails_without_repair(self):
        def action(call, context, schema):
            if call == 1:
                selection = next(item for item in context['available_actions'] if item.get('table') == 'reporting_log')
                return {key: selection[key] for key in ('type', 'tool', 'arguments')}
            proposal = review_brief(context)
            record = context['follow_up_result']['data']['records'][0]
            self.assertEqual('reporting_log', record['table'])
            proposal['evidence_ids'] = [record['ref']] * 20
            return proposal
        provider = CpuProvider(SimulatedClock(), callback=action)
        result = self.run_cpu(provider)
        self.assertEqual('invalid_list', result['failure_reason'])
        self.assertEqual(2, result['model_calls'])
        self.assertEqual(0, result['repairs'])
        self.assertIsNone(result['candidate_brief'])
        self.assertTrue(any(event['kind'] == 'validation_error' and event['code'] == 'invalid_list'
                            for event in result['trace']))

    def test_one_evidence_followup_is_valid_and_full_records_stay_in_receipt(self):
        provider = CpuProvider(SimulatedClock(), follow_up='get_evidence_records')
        result = self.run_cpu(provider)
        self.assertEqual('ready_for_review', result['execution_status'], result['failure_reason'])
        followups = [event for event in result['trace'] if event['kind'] == 'tool' and not event['mandatory']]
        self.assertEqual(1, len(followups))
        self.assertEqual('get_evidence_records', followups[0]['name'])
        for record in followups[0]['result']['records']:
            original_id = result['reference_aliases']['evidence'][record['ref']]
            original = next(item for item in result['evidence_bundle']['evidence_records'] if item['evidence_id'] == original_id)
            self.assertEqual(original['record'], record['record'])

    def test_final_timeout_is_clamped_and_first_reserves_final_capacity(self):
        provider = CpuProvider(SimulatedClock(), [134.14, 138.41])
        result = self.run_cpu(provider, budget=Budget(model_timeout_seconds=300, deadline_seconds=300))
        self.assertEqual('ready_for_review', result['execution_status'], result['failure_reason'])
        self.assertEqual(150, provider.requests[0]['timeout'])
        self.assertAlmostEqual(165.86, provider.requests[1]['timeout'])
        self.assertEqual(300, result['deadline_seconds'])
        self.assertEqual(300, result['model_timeout_seconds'])

    def test_baseline_time_reduces_followup_capacity_before_dispatch(self):
        clock = SimulatedClock()
        provider = CpuProvider(clock, [100, 275])
        def recall(query, *, memory_as_of_utc):
            clock.advance(150)
            return dict(mode='hmem_reference', memory_as_of_utc=memory_as_of_utc,
                        notes=[], pending_sync=0, limitations=[])
        result = self.run_cpu(provider, recall=recall, memory_as_of_utc='2026-01-15T00:00:00Z')
        self.assertEqual('ready_for_review', result['execution_status'], result['failure_reason'])
        self.assertEqual([150, 300], [request['timeout'] for request in provider.requests])

    def test_invalid_first_action_cannot_consume_reserved_final_call_as_repair(self):
        provider = CpuProvider(SimulatedClock(), callback=lambda *args: 'not JSON')
        result = self.run_cpu(provider)
        self.assertEqual('invalid_json', result['failure_reason'])
        self.assertEqual(1, result['model_calls'])
        self.assertEqual(0, result['repairs'])
        self.assertIsNone(result['candidate_brief'])

    def test_inadequate_model_or_tool_budget_fails_before_model_dispatch(self):
        for budget, reason in ((Budget(model_calls=1), 'brief_capacity_unavailable'),
                               (Budget(tool_calls=3), 'tool_budget_exhausted')):
            with self.subTest(reason=reason):
                provider = CpuProvider(SimulatedClock())
                result = self.run_cpu(provider, budget=budget)
                self.assertEqual(reason, result['failure_reason'])
                self.assertEqual(0, result['model_calls'])
                self.assertEqual([], provider.requests)

    def test_insufficient_time_for_reserved_brief_blocks_first_dispatch(self):
        clock = SimulatedClock()
        provider = CpuProvider(clock)
        def recall(query, *, memory_as_of_utc):
            clock.advance(301)
            return dict(mode='hmem_reference', memory_as_of_utc=memory_as_of_utc,
                        notes=[], pending_sync=0, limitations=[])
        result = self.run_cpu(provider, recall=recall, memory_as_of_utc='2026-01-15T00:00:00Z')
        self.assertEqual('brief_capacity_unavailable', result['failure_reason'])
        self.assertEqual(0, result['model_calls'])
        self.assertEqual([], provider.requests)

    def test_duplicate_baseline_is_rejected_without_reexecution(self):
        for view in ('canonical', 'raw_diagnostic'):
            with self.subTest(view=view):
                provider = CpuProvider(SimulatedClock(), callback=lambda *args: dict(
                    type='tool_call', tool='compare_monthly_indicators', arguments={'view': view}))
                result = self.run_cpu(provider)
                self.assertEqual('repeated_tool_call', result['failure_reason'])
                self.assertEqual(1, result['model_calls'])
                self.assertEqual(3, result['tool_calls'])
                self.assertEqual(0, result['repairs'])

    def test_second_request_cannot_explore_or_repeat_completed_followup(self):
        for repeat in (False, True):
            with self.subTest(repeat=repeat):
                first_action = []
                def action(call, context, schema):
                    if call == 1:
                        first_action.append(next(item for item in exact_tools(schema) if item['tool'] == 'compare_matched_facilities'))
                        return first_action[0]
                    if repeat:
                        return first_action[0]
                    return dict(type='tool_call', tool='get_evidence_records', arguments={
                        'evidence_ids': [context['reporting_quality']['source_index'][0]['ref']]})
                provider = CpuProvider(SimulatedClock(), callback=action)
                result = self.run_cpu(provider)
                self.assertEqual('repeated_tool_call' if repeat else 'action_not_available', result['failure_reason'])
                self.assertEqual(2, result['model_calls'])
                self.assertEqual(4, result['tool_calls'])
                self.assertEqual(0, result['repairs'])

    def test_early_brief_is_never_accepted(self):
        def action(call, context, schema):
            refs = [fact['ref'] for fact in context['canonical']['facts']][:2]
            return dict(type='propose_brief', explanation='reporting_artefact_supported', metric_refs=refs,
                        evidence_ids=[context['reporting_quality']['source_index'][0]['ref']], review_context_ids=[],
                        limitations=['synthetic_data', 'no_causal_attribution'], next_checks=['human_review'])
        provider = CpuProvider(SimulatedClock(), callback=action)
        result = self.run_cpu(provider)
        self.assertEqual('follow_up_required', result['failure_reason'])
        self.assertEqual(1, result['model_calls'])
        self.assertIsNone(result['candidate_brief'])

    def test_final_brief_retains_category_metric_period_and_authority_validation(self):
        for change, reason in (
            ('category', 'explanation_not_supported_by_facts'),
            ('metrics', 'missing_supporting_metrics'),
            ('period', 'missing_period_evidence'),
            ('approval', 'invalid_fields'),
            ('review_limitations', 'missing_review_limitations'),
            ('review_check', 'missing_review_limitations'),
            ('missing_field', 'invalid_fields'),
            ('evidence_selection', 'evidence_selection_not_available'),
        ):
            with self.subTest(change=change):
                def action(call, context, schema):
                    if call == 1:
                        return exact_tools(schema)[0]
                    proposal = review_brief(context)
                    if change == 'category':
                        proposal['explanation'] = 'testing_change_supported'
                    elif change == 'metrics':
                        proposal['metric_refs'].pop()
                    elif change == 'period':
                        proposal['evidence_ids'] = [context['reporting_quality']['source_index'][0]['ref']]
                    elif change == 'approval':
                        proposal['approval'] = True
                    elif change == 'review_check':
                        proposal['next_checks'] = ['review_source_versions']
                    elif change == 'missing_field':
                        proposal.pop('next_checks')
                    elif change == 'evidence_selection':
                        proposal['evidence_ids'].reverse()
                    else:
                        proposal['limitations'] = ['synthetic_data']
                    return proposal
                provider = CpuProvider(SimulatedClock(), callback=action)
                result = self.run_cpu(provider)
                self.assertEqual(reason, result['failure_reason'])
                self.assertEqual(2, result['model_calls'])
                self.assertEqual(0, result['repairs'])
                self.assertIsNone(result['candidate_brief'])

    def test_valid_but_unseen_registry_references_are_rejected(self):
        bundle = self.bundle()
        data = bundle.to_dict()
        for kind, key, source, field, reason in (
            ('metric', 'metrics', data['metrics'], 'metric_refs', 'unknown_or_unseen_metric_reference'),
            ('raw_metric', 'metrics', data['metrics'], 'metric_refs', 'unknown_or_unseen_metric_reference'),
            ('evidence', 'evidence', data['evidence_records'], 'evidence_ids', 'unknown_or_unseen_evidence_reference'),
        ):
            with self.subTest(kind=kind):
                bad_refs = []
                def action(call, context, schema):
                    if call == 1:
                        name = 'get_evidence_records' if kind == 'metric' else 'compare_matched_facilities'
                        return next(item for item in exact_tools(schema) if item['tool'] == name)
                    proposal = review_brief(context)
                    if kind == 'metric':
                        index = next(i for i, item in enumerate(source, 1) if item['cohort'] == 'matched')
                        known = context['canonical']['facts'][0]['ref']
                    elif kind == 'raw_metric':
                        index = next(i for i, item in enumerate(source, 1)
                                     if item['view'] == 'raw_diagnostic' and item['name'] == 'tested_total')
                        known = context['raw']['facts'][0]['ref']
                    else:
                        index = next(i for i, item in enumerate(source, 1) if item['table'] == 'facility_registry')
                        known = context['reporting_quality']['source_index'][0]['ref']
                    alias = known.rsplit('_', 1)[0] + f'_{index:02d}'
                    bad_refs.append(alias)
                    proposal[field].append(alias)
                    return proposal
                provider = CpuProvider(SimulatedClock(), callback=action)
                result = self.run_cpu(provider, bundle=bundle)
                self.assertEqual(reason, result['failure_reason'])
                self.assertIn(bad_refs[0], result['reference_aliases'][key])
                self.assertIsNone(result['candidate_brief'])

    def test_earlier_cutoff_never_exposes_future_report_versions(self):
        bundle = self.bundle('fx_a061c452', '2025-12-10T00:00:00Z')
        def action(call, context, schema):
            self.assertTrue(all(item['version'] != 2 for item in context['reporting_quality']['source_index']))
            return exact_tools(schema)[0] if call == 1 else review_brief(context, 'no_canonical_change')
        result = self.run_cpu(CpuProvider(SimulatedClock(), callback=action), bundle=bundle)
        self.assertEqual('ready_for_review', result['execution_status'], result['failure_reason'])
        self.assertFalse(any(item['record'].get('report_version') == 2 for item in result['evidence_bundle']['evidence_records']))

    def test_provider_failures_remain_distinct_without_fallback_or_error_secrets(self):
        for exception, reason in ((ProviderError('model_timeout'), 'model_timeout'),
                                  (ProviderError('model_transport_error'), 'model_transport_error'),
                                  (RuntimeError('secret-token'), 'model_provider_unavailable')):
            with self.subTest(reason=reason):
                def fail(*args):
                    raise exception
                provider = CpuProvider(SimulatedClock(), callback=fail)
                provider.mode = 'ollama'
                result = self.run_cpu(provider)
                self.assertEqual(reason, result['failure_reason'])
                self.assertEqual('ollama', result['model_mode'])
                self.assertEqual(1, result['model_calls'])
                self.assertIsNone(result['candidate_brief'])
                self.assertNotIn('secret-token', json.dumps(result))
                self.assertTrue(result['evidence_bundle']['metrics'])

    def test_response_after_request_timeout_or_overall_deadline_is_rejected(self):
        for durations, budget, reason in (
            ([151], Budget(model_timeout_seconds=300, deadline_seconds=300), 'model_timeout'),
            ([601], Budget(model_timeout_seconds=300), 'deadline_exceeded'),
            ([134.14, 466], Budget(model_timeout_seconds=300), 'deadline_exceeded'),
        ):
            with self.subTest(durations=durations):
                provider = CpuProvider(SimulatedClock(), durations)
                result = self.run_cpu(provider, budget=budget)
                self.assertEqual(reason, result['failure_reason'])
                self.assertIsNone(result['candidate_brief'])
                self.assertLessEqual(result['model_calls'], 2)

    def test_cancellation_before_dispatch_and_during_response_never_accepts_brief(self):
        provider = CpuProvider(SimulatedClock())
        result = self.run_cpu(provider, cancelled=lambda: True)
        self.assertEqual('cancelled', result['execution_status'])
        self.assertEqual(0, result['model_calls'])
        provider = CpuProvider(SimulatedClock(), [134.14, 138.41])
        result = self.run_cpu(provider, cancelled=lambda: provider.clock.elapsed > 200)
        self.assertEqual('cancelled', result['execution_status'])
        self.assertEqual(2, result['model_calls'])
        self.assertIsNone(result['candidate_brief'])

    def test_deadline_and_cancellation_during_final_render_prevent_candidate_acceptance(self):
        original_render = ToolSession.render
        for reason in ('deadline_exceeded', 'cancelled'):
            with self.subTest(reason=reason):
                clock = SimulatedClock()
                provider = CpuProvider(clock)
                cancellation = [False]
                rendered = []
                def render(session, action):
                    candidate = original_render(session, action)
                    rendered.append(candidate)
                    if reason == 'deadline_exceeded':
                        clock.advance(601)
                    else:
                        cancellation[0] = True
                    return candidate
                with patch.object(ToolSession, 'render', render):
                    result = self.run_cpu(provider, cancelled=lambda: cancellation[0])
                self.assertEqual(1, len(rendered))
                self.assertEqual(reason, result['failure_reason'])
                self.assertEqual('cancelled' if reason == 'cancelled' else 'failed', result['execution_status'])
                self.assertEqual('not_ready', result['review_status'])
                self.assertEqual(2, result['model_calls'])
                self.assertIsNone(result['candidate_brief'])


if __name__ == '__main__':
    unittest.main()
