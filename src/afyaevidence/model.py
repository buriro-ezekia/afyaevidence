"""Explicit scripted and local Ollama providers. No discovery scans or fallback."""
import json
import re
import time
from urllib.parse import urlsplit
import urllib.request

from .agent import ACTION_SCHEMA


class ProviderError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


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
        if path not in ('/api/tags','/api/chat') or not 0<timeout<=180:
            raise ProviderError('Invalid provider request')
        payload=None if body is None else json.dumps(body,separators=(',',':'),allow_nan=False).encode()
        if payload is not None and len(payload)>100000: raise ProviderError('Model context exceeds byte budget')
        request=urllib.request.Request(self.endpoint+path,data=payload,headers={'Content-Type':'application/json'})
        try:
            with self.opener.open(request,timeout=timeout) as response:
                data=response.read(262145)
                if response.status!=200 or len(data)>262144: raise ProviderError('Model response exceeds bounds')
            result=json.loads(data)
            if not isinstance(result,dict): raise ProviderError('Malformed provider response')
            return result
        except Exception:
            raise ProviderError('Ollama unavailable, timed out or returned an invalid response; no fallback') from None

    def models(self):
        result=self.request('/api/tags')
        if not isinstance(result.get('models'),list) or len(result['models'])>100:
            raise ProviderError('Invalid model listing')
        names=[m.get('name') for m in result['models'] if isinstance(m,dict)]
        if any(not isinstance(n,str) or not re.fullmatch(r'[A-Za-z0-9_./:-]{1,120}',n) for n in names):
            raise ProviderError('Invalid model identifier in listing')
        return names

    def next_action(self,messages,*,timeout):
        start=time.monotonic()
        result=self.request('/api/chat',dict(model=self.model,messages=messages,stream=False,
            format=ACTION_SCHEMA,options=dict(temperature=0,num_predict=768,num_ctx=8192)),timeout=timeout)
        message=result.get('message')
        if (result.get('done') is not True or result.get('model')!=self.model or not isinstance(message,dict) or
            not isinstance(message.get('content'),str) or len(message['content'].encode())>16384):
            raise ProviderError('Incomplete or mismatched model response')
        usage={}
        for field in ('prompt_eval_count','eval_count'):
            value=result.get(field)
            if value is not None and (type(value) is not int or value<0):
                raise ProviderError('Invalid model usage metadata')
            usage[field]=value
        return dict(content=message['content'],model=self.model,usage=usage,elapsed_seconds=time.monotonic()-start)


class ScriptedProvider:
    """Deterministic fixture exercise, explicitly not model inference or an answer key."""
    mode='scripted'
    model='scripted-policy-1'

    def __init__(self): self.calls=0

    def next_action(self,messages,*,timeout):
        baseline=next(json.loads(m['content']) for m in messages if m['role']=='user' and 'reporting_quality' in m['content'])
        if self.calls==0:
            action=dict(type='tool_call',tool='compare_monthly_indicators',arguments=dict(view='raw_diagnostic'))
        elif self.calls==1:
            action=dict(type='tool_call',tool='compare_matched_facilities',arguments=dict(include_contributions=True))
        else:
            raw=next(json.loads(m['content'])['data']['facts'] for m in messages if m['role']=='user' and
                     json.loads(m['content']).get('tool_result')=='compare_monthly_indicators')
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
                evidence_ids=[r['ref'] for r in baseline['reporting_quality']['source_index']][:20],
                review_context_ids=[n['ref'] for n in notes],limitations=limitations,
                next_checks=['review_source_versions','request_facility_context','human_review'])
        self.calls+=1
        return dict(content=json.dumps(action),model=self.model,usage=None,elapsed_seconds=0)
