"""Explicit scripted and local Ollama providers. No discovery scans or fallback."""
import json
import re
import time
from urllib.parse import urlsplit
import urllib.error
import urllib.request

from .agent import ACTION_SCHEMA


class ProviderError(RuntimeError):
    def __init__(self,code,*,request_metadata=None,elapsed_seconds=None):
        self.code=code
        self.request_metadata=request_metadata
        self.elapsed_seconds=elapsed_seconds
        super().__init__(code)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def encode_payload(value):
    """The exact compact UTF-8 encoding used on the wire; never a token estimate."""
    try:
        return json.dumps(value,separators=(',',':'),allow_nan=False,ensure_ascii=False).encode('utf-8')
    except (ValueError,TypeError,RecursionError,UnicodeError):
        raise ProviderError('model_invalid_request') from None


class OllamaProvider:
    mode='ollama'

    def __init__(self,*,endpoint='http://127.0.0.1:8082',model='qwen2.5:3b'):
        parsed=urlsplit(endpoint)
        if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or
            parsed.query or parsed.fragment or parsed.path not in ('','/')):
            raise ValueError('Use an explicit Ollama HTTP(S) origin without credentials or path')
        if not re.fullmatch(r'[A-Za-z0-9_./:-]{1,120}',model):
            raise ValueError('Invalid model identifier')
        self.endpoint=endpoint.rstrip('/')
        self.model=model
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

    def request(self,path,body=None,timeout=30):
        if path not in ('/api/tags','/api/chat') or type(timeout) not in (int,float) or not 0<timeout<=300:
            raise ProviderError('model_invalid_request')
        payload=None if body is None else encode_payload(body)
        if payload is not None and len(payload)>100000: raise ProviderError('model_context_limit')
        request=urllib.request.Request(self.endpoint+path,data=payload,headers={'Content-Type':'application/json'})
        try:
            with self.opener.open(request,timeout=timeout) as response:
                data=response.read(262145)
                if response.status!=200 or len(data)>262144: raise ProviderError('model_response_limit')
            result=json.loads(data)
            if not isinstance(result,dict): raise ProviderError('model_invalid_response')
            return result
        except ProviderError: raise
        except TimeoutError:
            raise ProviderError('model_timeout') from None
        except urllib.error.HTTPError:
            raise ProviderError('model_http_error') from None
        except urllib.error.URLError as exc:
            raise ProviderError('model_timeout' if isinstance(exc.reason,TimeoutError) else 'model_transport_error') from None
        except OSError:
            raise ProviderError('model_transport_error') from None
        except (ValueError,RecursionError):
            raise ProviderError('model_invalid_response') from None

    def models(self):
        result=self.request('/api/tags')
        if not isinstance(result.get('models'),list) or len(result['models'])>100:
            raise ProviderError('model_invalid_response')
        names=[m.get('name') for m in result['models'] if isinstance(m,dict)]
        if any(not isinstance(n,str) or not re.fullmatch(r'[A-Za-z0-9_./:-]{1,120}',n) for n in names):
            raise ProviderError('model_invalid_response')
        return names

    def build_request(self,messages,*,action_schema=None):
        """One phase schema in format; the host supplies the scoped phase prompt."""
        return dict(model=self.model,messages=messages,stream=False,
            format=ACTION_SCHEMA if action_schema is None else action_schema,
            options=dict(temperature=0,num_predict=768,num_ctx=8192))

    def request_metadata(self,body):
        return dict(request_bytes=len(encode_payload(body)),messages_bytes=len(encode_payload(body['messages'])),
                    schema_bytes=len(encode_payload(body['format'])),message_count=len(body['messages']))

    def next_action(self,messages,*,timeout,action_schema=None):
        start=time.monotonic()
        body=self.build_request(messages,action_schema=action_schema)
        metadata=self.request_metadata(body)
        try:
            result=self.request('/api/chat',body,timeout=timeout)
            message=result.get('message')
            if (result.get('done') is not True or result.get('model')!=self.model or not isinstance(message,dict) or
                not isinstance(message.get('content'),str) or len(message['content'].encode())>16384):
                raise ProviderError('model_incomplete_or_mismatched')
            usage={}
            # Ollama reports durations in nanoseconds. Preserve supplied counts and
            # timings as-is; missing values are unknown, never inferred from bytes.
            for field in ('prompt_eval_count','eval_count','prompt_eval_cached_count',
                          'total_duration','load_duration','prompt_eval_duration','eval_duration'):
                value=result.get(field)
                if value is not None and (type(value) is not int or value<0):
                    raise ProviderError('model_invalid_response')
                usage[field]=value
            return dict(content=message['content'],model=self.model,usage=usage,
                        request_metadata=metadata,elapsed_seconds=time.monotonic()-start)
        except ProviderError as exc:
            exc.request_metadata=metadata
            exc.elapsed_seconds=time.monotonic()-start
            raise


class ScriptedProvider:
    """Deterministic fixture exercise, explicitly not model inference or an answer key."""
    mode='scripted'
    model='scripted-policy-1'

    def __init__(self): self.calls=0

    def next_action(self,messages,*,timeout,action_schema=None):
        baseline=next(json.loads(m['content']) for m in messages if m['role']=='user' and 'reporting_quality' in m['content'])
        cpu=baseline.get('execution_profile')=='cpu'
        if cpu and baseline['phase']=='follow_up':
            choices=[]
            for branch in action_schema.get('oneOf',[action_schema]):
                fields=branch['properties']
                if fields['type'].get('const')=='tool_call':
                    choices.append(dict(type='tool_call',tool=fields['tool']['const'],
                        arguments={key:value['const'] for key,value in fields['arguments']['properties'].items()}))
            action=next(a for a in choices if a['tool']=='compare_matched_facilities' and
                        a['arguments']['include_contributions'] is True)
        elif not cpu and self.calls==0:
            action=dict(type='tool_call',tool='compare_monthly_indicators',arguments=dict(view='raw_diagnostic'))
        elif not cpu and self.calls==1:
            action=dict(type='tool_call',tool='compare_matched_facilities',arguments=dict(include_contributions=True))
        else:
            raw=baseline['raw']['facts'] if cpu else next(json.loads(m['content'])['data']['facts'] for m in messages
                if m['role']=='user' and json.loads(m['content']).get('tool_result')=='compare_monthly_indicators')
            facts=baseline['canonical']['facts']
            def metric(items,period,name): return next(f for f in items if f['period']==period and f['name']==name)
            a=metric(facts,'comparison','positive_total'); b=metric(facts,'target','positive_total')
            if a['availability']!='available' or b['availability']!='available': code='insufficient_data'
            else:
                delta=b['value']-a['value']
                raw_delta=metric(raw,'target','positive_total')['value']-metric(raw,'comparison','positive_total')['value']
                if delta==0 and raw_delta>0: code='reporting_artefact_supported'
                elif delta>0 and raw_delta>delta: code='mixed'
                elif delta>0 and metric(facts,'target','tested_total')['value']>metric(facts,'comparison','tested_total')['value'] and metric(facts,'target','positivity_pct')['value']==metric(facts,'comparison','positivity_pct')['value']:
                    code='testing_change_supported'
                elif delta==0: code='no_canonical_change'
                else: code='unexplained'
            notes=baseline.get('review_context',{}).get('notes',[])
            limitations=['synthetic_data','no_causal_attribution']
            if code=='insufficient_data': limitations.append('coverage_difference')
            if notes: limitations.append('historical_memory_only')
            action=dict(type='propose_brief',explanation=code,metric_refs=baseline['brief_requirements'][code],
                evidence_ids=action_schema['properties']['evidence_ids']['enum'][0] if cpu else
                             [r['ref'] for r in baseline['reporting_quality']['source_index']][:20],
                review_context_ids=[n['ref'] for n in notes],limitations=limitations,
                next_checks=['review_source_versions','request_facility_context','human_review'])
        self.calls+=1
        return dict(content=json.dumps(action),model=self.model,usage=None,elapsed_seconds=0)
