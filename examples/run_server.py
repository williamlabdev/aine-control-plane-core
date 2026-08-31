"""Serve the reference control plane locally so the UI has something to show.

    python3 examples/run_server.py --db ./control-plane.sqlite

Then, from ui/: `npm install && npm run dev`, and open the printed URL with
VITE_API_BASE_URL pointing at this server (http://127.0.0.1:8787 by default).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from aine_control_plane_core.adapters import StaticIdentityAdapter
from aine_control_plane_core.server import serve
from aine_control_plane_core.service import ControlPlaneService
from aine_control_plane_core.store import LocalRecordStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the reference control-plane server")
    parser.add_argument("--db", default="control-plane.sqlite")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    service = ControlPlaneService(
        LocalRecordStore(Path(args.db)),
        identity_adapter=StaticIdentityAdapter(
            {"self": {"id": "developer", "roles": ["approver"], "teams": ["platform"]}}
        ),
    )
    print(f"reference control plane on http://{args.host}:{args.port}")
    serve(service, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
