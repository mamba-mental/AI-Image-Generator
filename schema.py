"""
Normalize a provider's JSON-schema-style input properties into a FormSpec:
a flat list of field dicts the UI (webui/form.js) renders directly.

Field: {name, widget, label, default?, enum?, min?, max?, step?, kind?}
widget in: select | slider | number | toggle | text | loras | image

Type->widget precedence mirrors the old Tkinter builder (app.py:2891
_create_param_widget): loras/image special-cases first, then enum->select,
bool->toggle, ranged-number->slider, number->number, else text.
"""

# params that are handled elsewhere (main prompt box, plumbing) — never rendered as form fields
SKIP = {"prompt", "sync_mode", "enable_prompt_expansion"}
IMAGE_FIELDS = {"image_url", "image_urls", "start_image_url", "end_image_url"}


def _label(name):
    return name.replace("_", " ").strip().title()


def field_for(name, prop):
    """Map one schema property to a FormSpec field (or None to skip)."""
    if name in SKIP:
        return None
    # unwrap anyOf/oneOf/$ref-style unions: take the branch that carries enum/type
    if "anyOf" in prop or "oneOf" in prop:
        branches = prop.get("anyOf") or prop.get("oneOf") or []
        merged = dict(prop)
        for b in branches:
            if isinstance(b, dict) and ("enum" in b or b.get("type") not in (None, "null")):
                merged = {**b, **{k: prop[k] for k in ("default", "description", "title") if k in prop}}
                break
        prop = merged

    typ = prop.get("type")
    default = prop.get("default")
    base = {"name": name, "label": prop.get("title") or _label(name)}
    if "description" in prop:
        base["desc"] = prop["description"][:120]

    # --- special widgets first ---
    if name == "loras" or (typ == "array" and name.endswith("loras")):
        return {**base, "widget": "loras"}
    if name in IMAGE_FIELDS:
        return {**base, "widget": "image", "multi": name.endswith("s")}

    # --- enum -> select (wins over numeric/bool, matching the old builder) ---
    enum = prop.get("enum")
    if enum:
        return {**base, "widget": "select", "enum": [str(v) for v in enum],
                "default": str(default) if default is not None else str(enum[0])}

    if typ == "boolean":
        return {**base, "widget": "toggle", "default": bool(default)}

    if typ in ("integer", "number"):
        lo, hi = prop.get("minimum"), prop.get("maximum")
        is_int = typ == "integer"
        if lo is not None and hi is not None:
            step = 1 if is_int else (prop.get("multipleOf") or 0.1)
            return {**base, "widget": "slider", "min": lo, "max": hi, "step": step,
                    "int": is_int, "default": default if default is not None else lo}
        return {**base, "widget": "number", "int": is_int,
                "default": default if default is not None else (0 if is_int else 0.0)}

    if typ == "array":
        return None  # unknown array (not loras) — skip rather than guess

    # string / anything else -> text
    return {**base, "widget": "text", "default": "" if default is None else str(default)}


def props_to_formspec(properties, required=None):
    """properties: dict name->schema-property. Returns ordered FormSpec list."""
    required = set(required or [])
    spec = []
    for name, prop in (properties or {}).items():
        if not isinstance(prop, dict):
            continue
        f = field_for(name, prop)
        if f:
            f["required"] = name in required
            spec.append(f)
    return spec


if __name__ == "__main__":
    # self-check (ponytail: one runnable check for the money-path logic)
    fields = props_to_formspec({
        "mode": {"type": "string", "enum": ["a", "b"]},
        "flag": {"type": "boolean", "default": True},
        "steps": {"type": "integer", "minimum": 1, "maximum": 50, "default": 8},
        "count": {"type": "integer", "default": 4},
        "label": {"type": "string"},
        "loras": {"type": "array", "items": {}},
        "image_url": {"type": "string"},
        "prompt": {"type": "string"},  # must be skipped
    }, required=["mode"])
    by = {f["name"]: f["widget"] for f in fields}
    assert by == {"mode": "select", "flag": "toggle", "steps": "slider",
                  "count": "number", "label": "text", "loras": "loras",
                  "image_url": "image"}, by
    assert next(f for f in fields if f["name"] == "mode")["required"] is True
    # anyOf unwrap (fal image_size shape)
    isz = field_for("image_size", {"anyOf": [{"enum": ["square", "portrait_3_4"]}, {"type": "object"}],
                                   "default": "square"})
    assert isz["widget"] == "select" and "portrait_3_4" in isz["enum"], isz
    print("schema.py self-check OK")
