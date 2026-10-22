#!/usr/bin/env python3
"""Exercise actual pinned H-MEM persistence/provenance/scope with synthetic notes."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from afyaevidence.analysis import investigate
from afyaevidence.memory import HmemBridge, ReviewStore, Scope, PIN
from afyaevidence.snapshot import FixtureGateway


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis',type=Path,help='Prior analysis receipt supplying source provenance; no new JDBC call')
    parser.add_argument('--output',type=Path,help='Create a new check receipt without overwriting')
    parser.add_argument('--node',default='node')
    args=parser.parse_args(argv)
    try:
        if args.output and args.output.exists(): raise ValueError('Output exists')
        if args.analysis:
            raw=args.analysis.read_bytes()
            analysis=json.loads(raw)
            analysis_hash=hashlib.sha256(raw).hexdigest()
        else:
            analysis=investigate(FixtureGateway().collect(ROOT/'data/synthetic/fx_32e8b610')).to_dict()
            analysis_hash=None
        now=datetime.now(timezone.utc)
        reviewed=now.strftime('%Y-%m-%dT%H:%M:%SZ')
        cutoff=(now+timedelta(seconds=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
        with tempfile.TemporaryDirectory(prefix='afya-hmem-check-') as temp:
            root=Path(temp)
            reviews=ReviewStore(root/'reviews.sqlite3')
            scope=Scope('afya-synthetic-v1','D001')
            review_id='rv_'+uuid.uuid4().hex
            reviews.record_reviewed_note(scope=scope,review_id=review_id,
                snapshot_id=analysis['snapshot_id'],analysis_id=analysis['analysis_id'],
                note='Review report versions before interpreting changes in reported malaria counts.',
                reviewed_at_utc=reviewed,reviewer='operator-synthetic-integration-check')
            options=dict(root=root/'stores',bridge_dir=ROOT/'bridges/hmem',reviews=reviews,node=args.node)
            with HmemBridge(scope=scope,**options) as bridge:
                def crash(): raise RuntimeError('Synthetic crash window')
                try: bridge.sync(after_write=crash)
                except RuntimeError: pass
            with HmemBridge(scope=scope,**options) as bridge:
                bridge.sync()
                audit=bridge.audit()
                if len(audit['records'])!=1 or len(reviews.pending(scope))!=0: raise ValueError('Outbox failed')
                notes=bridge.recall('report versions',memory_as_of_utc=cutoff)['notes']
                if len(notes)!=1 or notes[0]['review_id']!=review_id: raise ValueError('Recall provenance failed')
                if bridge.recall('report versions',memory_as_of_utc='2000-01-01T00:00:00Z')['notes']:
                    raise ValueError('Chronology filter failed')
            for other in (Scope('afya-synthetic-v1','D002'),Scope('other-family','D001')):
                with HmemBridge(scope=other,**options) as bridge:
                    if bridge.recall('report versions',memory_as_of_utc=cutoff)['notes']: raise ValueError('Scope leaked')
        receipt=dict(engine='meterless-hmem-reference',upstream_commit=PIN,status='PASS',
            persistence='PASS',provenance='PASS',scope_isolation='PASS',chronology='PASS',outbox_retry='PASS',
            source_data_mode=analysis['data_mode'],source_snapshot_id=analysis['snapshot_id'],
            source_analysis_id=analysis['analysis_id'],source_analysis_receipt_sha256=analysis_hash,
            checked_at_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            review_kind='synthetic_operator_test; not a clinical approval',
            memory_as_of_utc=cutoff,model='NOT_RUN',live_zetaris='NOT_RUN_THIS_COMMAND',
            limitations='Mock hash embeddings; JSON persistence; local reference, not Meterless Runtime inference')
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open('x',encoding='utf-8') as stream: json.dump(receipt,stream,indent=2); stream.write('\n')
        print('HMEM_REFERENCE=PASS\nHMEM_PERSISTENCE=PASS\nHMEM_PROVENANCE=PASS\nHMEM_SCOPE_ISOLATION=PASS\nHMEM_CHRONOLOGY=PASS\nHMEM_OUTBOX_RETRY=PASS')
        print('LIVE_MODEL=NOT_RUN\nLIVE_ZETARIS=NOT_RUN_THIS_COMMAND')
        if args.output: print(f'RECEIPT={args.output}')
        return 0
    except (KeyboardInterrupt,EOFError):
        print('HMEM_REFERENCE=INTERRUPTED',file=sys.stderr)
        return 2
    except Exception:
        print('HMEM_REFERENCE=FAIL\nCheck Node 24, pinned sources, receipt and local storage; no fallback. Raw errors withheld.',file=sys.stderr)
        return 1


if __name__=='__main__': raise SystemExit(main())
