"""Populate static play metadata into dashboard state."""

from pathlib import Path

from src.cli.dashboard.state import DashboardState


def populate_play_meta(state: DashboardState, play: object) -> None:
    """Extract static metadata from a Play object into dashboard state."""
    # Features summary
    features = getattr(play, "features", ())
    if features:
        parts = []
        decls = []
        for f in features:
            ind = getattr(f, "indicator_type", "") or getattr(f, "structure_type", "")
            params = getattr(f, "params", {})
            length = params.get("length", "")
            tf = getattr(f, "tf", "") or ""
            name = getattr(f, "name", "") or getattr(f, "id", "") or ""
            label = f"{ind}({length})" if length else ind
            if tf:
                label += f"@{tf}"
            parts.append(label)
            params_str = ", ".join(f"{k}={v}" for k, v in params.items()) if params else ""
            decls.append((name, ind, tf, params_str))
        state.features_summary = ", ".join(parts)
        state.feature_decls = decls

    # Actions summary
    actions = getattr(play, "actions", [])
    if actions:
        state.actions_summary = ", ".join(getattr(b, "id", "?") for b in actions)

    # Position policy
    policy = getattr(play, "position_policy", None)
    if policy:
        state.position_mode = getattr(policy.mode, "value", str(policy.mode))
        state.exit_mode = getattr(policy.exit_mode, "value", str(policy.exit_mode))

    # Risk model
    rm = getattr(play, "risk_model", None)
    if rm:
        sl = rm.stop_loss
        sl_type = getattr(sl.type, "value", str(sl.type))
        if "atr" in sl_type:
            state.sl_summary = f"ATR {sl.value}x"
        elif "pct" in sl_type or "percent" in sl_type:
            state.sl_summary = f"{sl.value}%"
        else:
            state.sl_summary = f"{sl_type} {sl.value}"

        tp = rm.take_profit
        tp_type = getattr(tp.type, "value", str(tp.type))
        if "rr" in tp_type:
            state.tp_summary = f"RR {tp.value}:1"
        elif "atr" in tp_type:
            state.tp_summary = f"ATR {tp.value}x"
        elif "pct" in tp_type or "percent" in tp_type:
            state.tp_summary = f"{tp.value}%"
        else:
            state.tp_summary = f"{tp_type} {tp.value}"

        sizing = rm.sizing
        model = getattr(sizing.model, "value", str(sizing.model))
        state.sizing_summary = f"{model} {sizing.value}%, max {sizing.max_leverage}x"

    # Max drawdown
    acct = getattr(play, "account", None)
    if acct:
        state.max_drawdown_pct = getattr(acct, "max_drawdown_pct", 0.0)

    # Structure declarations from features (features with structure_type set)
    if features:
        struct_decls = []
        for f in features:
            stype = getattr(f, "structure_type", None)
            if stype:
                key = getattr(f, "name", "") or getattr(f, "id", "") or "?"
                tf = getattr(f, "tf", "") or "exec"
                struct_decls.append((key, str(stype), tf))
        state.structure_decls = struct_decls

    # Full YAML source — search recursively like load_play() does
    play_id = getattr(play, "id", "") or getattr(play, "name", "")
    if play_id:
        try:
            plays_dir = Path("plays")
            if plays_dir.exists():
                for ext in (".yml", ".yaml"):
                    # Direct match first
                    candidate = plays_dir / f"{play_id}{ext}"
                    if candidate.exists():
                        state.play_yaml = candidate.read_text(encoding="utf-8")
                        break
                    # Recursive search (subdirectories)
                    matches = list(plays_dir.rglob(f"{play_id}{ext}"))
                    if matches:
                        state.play_yaml = matches[0].read_text(encoding="utf-8")
                        break
        except Exception:
            pass
