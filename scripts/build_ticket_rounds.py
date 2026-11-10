"""Build optional reviewed ticket sidecar without changing event data."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from .ticket_rounds import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--events', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--generated-at-utc', required=True)
    args = parser.parse_args()
    if args.output.resolve() in {args.ledger.resolve(), args.events.resolve()}:
        parser.error('output must not replace an input')
    payload = build(json.loads(args.ledger.read_text()), args.events.read_bytes(), generated_at_utc=args.generated_at_utc)
    content = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as f:
            name = f.name
            f.write(content); f.flush(); os.fsync(f.fileno())
        os.replace(name, args.output)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
    print(f'ticket rounds: {len(payload["rounds"])}; event links: {len(payload["links"])}')

if __name__ == '__main__': main()
