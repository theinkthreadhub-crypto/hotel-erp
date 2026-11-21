"""Review and replay counter sync ops that the cloud held back (BUG-0010 recovery).

    python tools/replay_held_ops.py --data DIR                 # dry run: prints the plan, changes nothing
    python tools/replay_held_ops.py --data DIR --apply         # queues the replays (needs --i-have-a-backup)

DIR is the counter data folder that holds setu.sqlite. Stop the counter first and take a backup. The tool never sends
anything itself: the counter's normal sync sends the queued replays and marks each one sent only on an exact
(op_id, hotel, checksum) acknowledgement. Ops listed under needs_review are never replayed automatically.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import setu_sqlite as S  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--data', required=True, help='counter data folder (contains setu.sqlite)')
    ap.add_argument('--apply', action='store_true', help='queue the planned replays')
    ap.add_argument('--i-have-a-backup', action='store_true', help='required with --apply')
    a = ap.parse_args(argv)
    if a.apply and not a.i_have_a_backup:
        ap.error('--apply changes the counter database: take a backup first and add --i-have-a-backup')
    sdb = S.SqliteDoc(os.path.join(a.data, S.DB_FILE))
    try:
        plan = S.plan_held_op_replay(sdb)
        summary = {
            'hotel_id': plan['hotel_id'], 'policy_version': plan['policy_version'],
            'replay': [{'op_id': i['op_id'], 'held_outbox_seq': i['outbox_seq'], 'bills': i['bills'], 'keys': i['envelope']['integrity']['keys'],
                        'dropped': i['dropped']} for i in plan['replay']],
            'needs_review': plan['needs_review'], 'nothing_to_send': plan['nothing_to_send'], 'already_replayed': plan['already_replayed'],
            'local_totals': {k: v for k, v in S.local_synced_bill_totals(sdb).items() if k != 'ids'},
        }
        if a.apply:
            summary['queued'] = S.apply_held_op_replay(sdb, plan)
        print(json.dumps(summary, indent=1, ensure_ascii=False))
    finally:
        sdb.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
