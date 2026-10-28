"""Rules shared by render_cut.py and synthesize_voice.py."""

from pathlib import Path

STYLES = {"walk", "scenic"}
DEFAULT_FIELD = {"walk": 1.0, "scenic": 0.3}


def field_level(decision):
    if decision.get("mute_field"):
        return 0.0
    value = decision.get("field_volume")
    if value is None:
        return DEFAULT_FIELD.get(decision.get("style") or "walk", 1.0)
    return max(0.0, min(1.0, float(value)))


def needs_dub(clip, level):
    """A clip carries narration when it has text but no field speech the viewer will hear."""
    if not (clip.get("subtitle") or "").strip():
        return False
    return level == 0 or not (clip.get("speech") or "").strip()


def voice_file(root, clip):
    return Path(root) / "board" / "voice" / f"{clip['id']}.wav"
