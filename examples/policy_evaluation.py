from aine_control_plane.contracts import AdapterContext
from aine_control_plane.governance import evaluate_policy


decision = evaluate_policy(
    {"policy_id": "release", "required_checks": ["tests", "security"]},
    [
        {"check_id": "tests", "status": "pass", "evidence_ids": ["evidence.tests"]},
        {"check_id": "security", "status": "unknown", "evidence_ids": ["evidence.security"]},
    ],
    AdapterContext("example-request", actor={"id": "developer"}),
    mode="enforced",
)

print(decision)
