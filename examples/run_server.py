"""Serve the reference control plane locally so the UI has something to show.

    PYTHONPATH=. python3 examples/run_server.py --db ./control-plane.sqlite

Then, from ui/: `npm ci --include=optional --ignore-scripts && npm run dev`,
and open the printed URL. The Vite
dev server proxies /v1 and /healthz to this server — do not set
VITE_API_BASE_URL for local development. To serve a production UI build from
a different origin instead, start this server with --cors-origin set to that
origin and build the UI with VITE_API_BASE_URL pointing here.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from aine_control_plane.adapters import StaticIdentityAdapter
from aine_control_plane.server import serve
from aine_control_plane.service import ControlPlaneService
from aine_control_plane.store import LocalRecordStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the reference control-plane server")
    parser.add_argument("--db", default="control-plane.sqlite")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument(
        "--cors-origin",
        default=None,
        help="allow cross-origin browser access from exactly this origin (default: off)",
    )
    args = parser.parse_args()

    service = ControlPlaneService(
        LocalRecordStore(Path(args.db)),
        identity_adapter=StaticIdentityAdapter(
            {"self": {"id": "developer", "roles": ["approver"], "teams": ["platform"]}}
        ),
    )
    print(f"reference control plane on http://{args.host}:{args.port}")
    serve(service, host=args.host, port=args.port, cors_origin=args.cors_origin)


if __name__ == "__main__":
    main()
