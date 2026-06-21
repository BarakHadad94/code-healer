from enum import Enum

from .config_loader import get_sensitive_paths


class ActivationReason(str, Enum):
    SELF_HEAL = "self_heal"
    DEEP_REVIEW = "deep_review"
    SKIPPED = "skipped"


_ACTIVATION_LABELS = {
    ActivationReason.SELF_HEAL: "Self-heal (tests failed)",
    ActivationReason.DEEP_REVIEW: "Deep review (sensitive path)",
    ActivationReason.SKIPPED: "Skipped (tests green, no sensitive paths)",
}


def activation_label(reason: str) -> str:
    try:
        return _ACTIVATION_LABELS[ActivationReason(reason)]
    except ValueError:
        return reason or "—"


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def find_sensitive_matches(files: list[str], sensitive_paths: list[str]) -> list[str]:
    """Return workspace-relative files that touch a configured sensitive prefix."""
    matched: list[str] = []
    prefixes = [_normalize(p).rstrip("/") for p in sensitive_paths]

    for raw in files:
        path = _normalize(raw)
        for prefix in prefixes:
            if path == prefix or path.startswith(prefix + "/"):
                matched.append(raw)
                break
    return matched


def decide_activation(
    tests_passed: bool,
    changed_files: list[str],
    file_path: str,
) -> tuple[ActivationReason, list[str]]:
    files_to_check = changed_files if changed_files else [file_path]
    sensitive_hits = find_sensitive_matches(files_to_check, get_sensitive_paths())

    if not tests_passed:
        return ActivationReason.SELF_HEAL, sensitive_hits
    if sensitive_hits:
        return ActivationReason.DEEP_REVIEW, sensitive_hits
    return ActivationReason.SKIPPED, []
