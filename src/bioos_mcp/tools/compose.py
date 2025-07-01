# bioos_mcp/tools/compose.py
import json, re
from typing import Any, Dict, List, Set, Tuple

# ---------- 1. 解析 (optional [, default = xxx]) -----------------------
_OPT_RE = re.compile(
    r"\(\s*optional(?:\s*,\s*default\s*=\s*([^)]+))?\s*\)",
    re.IGNORECASE,
)

def _parse_spec(spec: str) -> Tuple[str, Any]:
    """
    输入模板 value (str)，返回:
      kind     : 'required' | 'opt_def' | 'opt_nodef'
      default  : Python 值 (如果有)
    """
    m = _OPT_RE.search(spec)
    if not m:
        return "required", None

    default_raw = m.group(1)
    if default_raw is None:
        return "opt_nodef", None

    default_raw = default_raw.strip().strip('"\'')
    if default_raw.lower() in {"true", "false"}:
        return "opt_def", default_raw.lower() == "true"
    try:
        # 尝试数字
        if "." in default_raw:
            return "opt_def", float(default_raw)
        return "opt_def", int(default_raw)
    except ValueError:
        # 回退到字符串
        return "opt_def", default_raw


# ---------- 2. 把模板拆成 3 组 ----------------------------------------
def classify(tpl: Dict[str, str]):
    required: Set[str] = set()
    opt_def: Dict[str, Any] = {}
    opt_nodef: Set[str] = set()

    for k, v in tpl.items():
        kind, default = _parse_spec(v)
        if kind == "required":
            required.add(k)
        elif kind == "opt_def":
            opt_def[k] = default
        else:
            opt_nodef.add(k)
    return required, opt_def, opt_nodef


# ---------- 3. 单样本填充 ---------------------------------------------
def fill_one_sample(
    sample: Dict[str, Any],
    required: Set[str],
    opt_def: Dict[str, Any],
    opt_nodef: Set[str],
    template_keys: Set[str],
) -> Tuple[Dict[str, Any], List[str]]:
    """
    根据三条规则返回 (filled_dict, errors)
    """
    filled: Dict[str, Any] = {}
    errors: List[str] = []

    # ① 必填
    for k in required:
        if k not in sample:
            errors.append(f"缺少必填字段 {k}")
        else:
            filled[k] = sample[k]

    # ② 可选 + default
    for k, d in opt_def.items():
        filled[k] = sample.get(k, d)

    # ③ 可选 + 无 default（只有用户给了才写）
    for k in opt_nodef:
        if k in sample:
            filled[k] = sample[k]

    # ④ 检测多余键
    extra = set(sample) - template_keys
    if extra:
        errors.append(f"存在模板以外字段: {', '.join(extra)}")

    return filled, errors


# ---------- 4. 对外主函数 ---------------------------------------------
def build_inputs(template_path: str, samples: List[Dict[str, Any]]):
    """
    读模板 → 批量填充 → 返回 (filled_samples, error_msg)
    """
    with open(template_path, "r") as f:
        tpl = json.load(f)

    req, opt_def, opt_nodef = classify(tpl)
    tkeys = set(tpl)

    filled_all, all_errs = [], []
    for idx, s in enumerate(samples, 1):
        filled, errs = fill_one_sample(s, req, opt_def, opt_nodef, tkeys)
        if errs:
            all_errs.append(f"样本 #{idx}:\n" + "\n".join(errs))
        filled_all.append(filled)

    return filled_all, "\n\n".join(all_errs)
