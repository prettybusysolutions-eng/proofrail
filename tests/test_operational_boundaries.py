import concurrent.futures
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from integrations.openclaw.github_adapter import GitHubMergeAdapter
import proofrail.permit as permits
from proofrail.trust import create_trust_checkpoint,replay_registry_root

class OperationalBoundaryTests(unittest.TestCase):
    def test_already_merged_wrong_head_is_not_our_success(self):
        class Transport:
            def request(self, method, path, **kwargs):
                assert method=='GET'
                return 200,{}, {'merged':True,'merge_commit_sha':'c'*40,'head':{'sha':'b'*40}}
        result=GitHubMergeAdapter(Transport()).execute({'execution':{'owner':'fixture','repo':'fixture','pull_number':1,'expected_head_sha':'a'*40}},idempotency_key='test')
        self.assertEqual(result['status'],'failed')
        self.assertFalse(result['side_effect_confirmed'])

    def test_concurrent_distinct_permits_cannot_spend_same_checkpoint(self):
        now=datetime.now(timezone.utc)
        key=Ed25519PrivateKey.generate();trust_key=Ed25519PrivateKey.generate()
        with tempfile.TemporaryDirectory() as root:
            registry=Path(root)/'replay.sqlite'
            context=dict(public_key=key.public_key(),expected_identity_root='1'*64,expected_evidence_root='2'*64,expected_policy_root='3'*64,expected_state_root='4'*64,expected_approval_digest='5'*64,repository='fixture/fixture',pull_number=1,expected_head_sha='a'*40,merge_method='squash',executor_id='synthetic',registry_path=registry,now=now)
            def mint(nonce,trust=None):
                return permits.mint_permit(identity_root='1'*64,evidence_root='2'*64,policy_root='3'*64,state_root='4'*64,approval_digest='5'*64,repository='fixture/fixture',pull_number=1,expected_head_sha='a'*40,merge_method='squash',nonce=nonce,expires_at=now+timedelta(hours=1),issuer_principal_id='synthetic-verifier',issuer_role='verifier',private_key=key,key_id='synthetic',now=now,trust=trust)
            permits.consume_permit(mint('initial-seed-nonce-001'),**context)
            checkpoint=create_trust_checkpoint(replay_root=replay_registry_root(registry),epoch=1,monotonic_counter=1,private_key=trust_key,key_id='synthetic-checkpoint')
            trust=dict(replay_root=checkpoint['roots']['replay'],checkpoint_root=checkpoint['record_hash'],observation_root=checkpoint['roots']['observation'],minimum_checkpoint_epoch=1,monotonic_counter=1)
            candidates=[mint('concurrent-nonce-'+str(i),trust) for i in range(2)]
            barrier=threading.Barrier(2);original=permits.verify_permit
            def synchronized(*args,**kwargs):
                result=original(*args,**kwargs);barrier.wait(timeout=10);return result
            def consume(candidate):
                try:
                    permits.consume_permit(candidate,**context,trust_checkpoint=checkpoint,checkpoint_public_key=trust_key.public_key())
                    return 'CONSUMED'
                except permits.PermitError as exc:return exc.code
            with patch.object(permits,'verify_permit',side_effect=synchronized),concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(consume,candidates))
            self.assertEqual(results.count('CONSUMED'),1,results)
            self.assertEqual(results.count('replay_root_changed'),1,results)
