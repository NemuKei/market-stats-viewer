"""Append-only reviewed ticket snapshots; corrections never reuse an ID."""
import hashlib
import json
from .ticket_rounds import require, shape, utc


def facts_hash(snapshot):
    facts = {k: snapshot[k] for k in ('rounds', 'links')}
    return hashlib.sha256(json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_review(snapshot):
    shape(snapshot, {'rounds', 'links', 'review'})
    shape(snapshot['review'], {'status', 'facts_sha256', 'reviewed_at_utc'})
    review = snapshot['review']
    require(review['status'] == 'reviewed', 'review required')
    utc(review['reviewed_at_utc'])
    require(review['facts_sha256'] == facts_hash(snapshot), 'facts changed after review')
    require(isinstance(snapshot['rounds'], list) and isinstance(snapshot['links'], list), 'history lists required')
    from .ticket_rounds import validate
    validate(dict(schema_version=1, generated_at_utc=review['reviewed_at_utc'],
                  event_generation_sha256='0' * 64,
                  rounds=snapshot['rounds'], links=snapshot['links']),
             event_generation_sha256='0' * 64,
             event_uids={link['event_uid'] for link in snapshot['links']})
    ids = [r['ticket_round_id'] for r in snapshot['rounds']]
    require(len(ids) == len(set(ids)), 'duplicate historical ID')


def validate_history(ledger):
    """History excludes current snapshot. Checks full chain, not just last item.

    Git remains the durable audit storage. This detects accidental history drift;
    it does not cryptographically authenticate a reviewer or immutable storage.
    """
    require(isinstance(ledger['history'], list), 'history required')
    current = {k: ledger[k] for k in ('rounds', 'links', 'review')}
    previous = None
    for snapshot in [*ledger['history'], current]:
        validate_review(snapshot)
        rounds = {r['ticket_round_id']: r for r in snapshot['rounds']}
        if previous is None:
            require(all(type(r['revision']) is int and r['revision'] == 1 for r in rounds.values()), 'initial revision must be 1')
        else:
            prior = {r['ticket_round_id']: r for r in previous['rounds']}
            require(set(prior) <= set(rounds), 'historical round removal prohibited')
            require(previous['review']['reviewed_at_utc'] <= snapshot['review']['reviewed_at_utc'], 'review time regression')
            for uid, r in rounds.items():
                if uid not in prior:
                    require(type(r['revision']) is int and r['revision'] == 1, 'new revision must be 1')
                    continue
                old = prior[uid]
                require(r['first_seen_at_utc'] == old['first_seen_at_utc'], 'first seen changed')
                require(r['last_verified_at_utc'] >= old['last_verified_at_utc'], 'verification regression')
                old_links = {l['event_uid'] for l in previous['links'] if l['ticket_round_id'] == uid}
                new_links = {l['event_uid'] for l in snapshot['links'] if l['ticket_round_id'] == uid}
                changed = {k:v for k,v in r.items() if k != 'revision'} != {k:v for k,v in old.items() if k != 'revision'} or old_links != new_links
                require(type(r['revision']) is int and r['revision'] == old['revision'] + int(changed), 'revision must advance once per reviewed change')
        previous = snapshot
