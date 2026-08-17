#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_plugin.py - qamaster 插件结构自检

校验三平台（Claude Code / Codex / Cursor）适配层与 skills 结构完整性。
仅用 Python 标准库，CI 与本地均可运行。任一硬错误退出码 1。

用法：python scripts/check_plugin.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
errors = []
warnings = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        err(f"{path.relative_to(ROOT)}: 文件缺失")
        return None
    except json.JSONDecodeError as e:
        err(f"{path.relative_to(ROOT)}: JSON 解析失败 - {e}")
        return None


def parse_frontmatter(path):
    """返回 frontmatter 的 key/value dict；无 frontmatter 或格式错误返回 None。"""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    if not text.startswith("---"):
        return None
    m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", text, re.S)
    if not m:
        return None
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


# 1. Claude Code: plugin.json
p = load_json(ROOT / ".claude-plugin/plugin.json")
if p:
    for k in ("name", "version", "description"):
        if not p.get(k):
            err(f".claude-plugin/plugin.json: 缺少必填字段 {k}")

# 2. Claude Code: marketplace.json
mp = load_json(ROOT / ".claude-plugin/marketplace.json")
if mp:
    for k in ("name", "owner", "plugins"):
        if k not in mp:
            err(f".claude-plugin/marketplace.json: 缺少必填字段 {k}")
    plugins = mp.get("plugins") or []
    if not plugins:
        err(".claude-plugin/marketplace.json: plugins 列表为空")
    for pl in plugins:
        if not pl.get("name"):
            err(".claude-plugin/marketplace.json: plugin 条目缺少 name")
        if not pl.get("source"):
            err(f".claude-plugin/marketplace.json: plugin {pl.get('name')} 缺少 source")

# 3. skills/*/SKILL.md frontmatter
skills_dir = ROOT / "skills"
if not skills_dir.is_dir():
    err("skills/ 目录缺失")
else:
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        fm = parse_frontmatter(skill_md)
        if fm is None:
            err(f"{skill_md.relative_to(ROOT)}: 缺少 frontmatter 或格式错误")
            continue
        if not fm.get("name"):
            err(f"{skill_md.relative_to(ROOT)}: frontmatter 缺少 name")
        if not fm.get("description"):
            err(f"{skill_md.relative_to(ROOT)}: frontmatter 缺少 description")
        if fm.get("name") and fm["name"] != skill_dir.name:
            warn(f"{skill_md.relative_to(ROOT)}: frontmatter name='{fm.get('name')}' 与目录名 '{skill_dir.name}' 不一致")

# 4. commands/*.md frontmatter
cmd_dir = ROOT / "commands"
if cmd_dir.is_dir():
    for cmd in sorted(cmd_dir.glob("*.md")):
        fm = parse_frontmatter(cmd)
        if fm is None:
            err(f"{cmd.relative_to(ROOT)}: 缺少 frontmatter")
        elif not fm.get("description"):
            warn(f"{cmd.relative_to(ROOT)}: frontmatter 缺少 description")

# 5. .cursor/rules/*.mdc frontmatter
cursor_dir = ROOT / ".cursor/rules"
if cursor_dir.is_dir():
    for rule in sorted(cursor_dir.glob("*.mdc")):
        fm = parse_frontmatter(rule)
        if fm is None:
            err(f"{rule.relative_to(ROOT)}: 缺少 frontmatter")
        elif not fm.get("description"):
            warn(f"{rule.relative_to(ROOT)}: frontmatter 缺少 description")
else:
    warn(".cursor/rules/ 目录缺失（Cursor 适配未安装）")

# 6. Codex 适配必要文件
for must in (
    ROOT / "AGENTS.md",
    ROOT / "codex/prompts/case-design.md",
    ROOT / "codex/prompts/requirement-review.md",
):
    if not must.exists():
        err(f"{must.relative_to(ROOT)}: 缺失")

# 6.5 Runtime（Agent Runtime Engineering）结构完整性
rt_dir = ROOT / "runtime"
for must in (rt_dir / "qamaster_runtime.py", rt_dir / "state_store.py", rt_dir / "phases.py"):
    if not must.exists():
        err(f"{must.relative_to(ROOT)}: 缺失（Runtime 受控流程核心文件）")
if (rt_dir / "phases.py").exists():
    import importlib.util
    sys.path.insert(0, str(rt_dir))
    try:
        spec = importlib.util.spec_from_file_location("qamaster_phases", rt_dir / "phases.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        err(f"runtime/phases.py: 加载失败 - {e}")
        mod = None
    finally:
        try:
            sys.path.remove(str(rt_dir))
        except ValueError:
            pass
    if mod is not None:
        ids = [p["id"] for p in mod.PHASES]
        if ids != list(range(0, 16)):
            err("runtime/phases.py: 阶段编号必须连续 0-15，实际: %s" % ids)
        gates = {p["gate"] for p in mod.PHASES}
        if not gates <= {"auto", "confirm", "license"}:
            err("runtime/phases.py: 非法 gate 类型: %s" % gates)
        for pid, want in ((1, "confirm"), (14, "confirm"), (15, "license")):
            actual = mod.PHASE_BY_ID[pid]["gate"]
            if actual != want:
                err(f"runtime/phases.py: Phase {pid} gate 应为 {want}，实际 {actual}")
        for pid in (0, 13, 15):
            if not mod.PHASE_BY_ID[pid].get("gate_checks"):
                warn(f"runtime/phases.py: Phase {pid} 无机器检查项（建议至少一个确定性检查）")
        for p in mod.PHASES:
            for r in p.get("refs", []):
                if not (ROOT / "skills" / "case-design" / r).exists():
                    err(f"runtime/phases.py: Phase {p['id']} 引用的细则不存在: {r}")
if not (ROOT / "scripts" / "test_runtime.py").exists():
    warn("scripts/test_runtime.py: 缺失（Runtime 自证测试）")

# 6.6 多需求并行 + 通用 workflow 引擎结构护栏（回归 fence）
for must in (rt_dir / "locking.py", rt_dir / "manifest.py"):
    if not must.exists():
        err(f"{must.relative_to(ROOT)}: 缺失（多需求并行/共享索引核心文件）")
wf_dir = rt_dir / "workflows"
for must in (wf_dir / "__init__.py", wf_dir / "registry.py", wf_dir / "case_design.py"):
    if not must.exists():
        err(f"{must.relative_to(ROOT)}: 缺失（通用 workflow 注册表）")
# v0.11.10（缺陷4）：requirement-review 轻量状态机结构护栏
for must in (rt_dir / "requirement_review_phases.py", wf_dir / "requirement_review.py"):
    if not must.exists():
        err(f"{must.relative_to(ROOT)}: 缺失（requirement-review workflow 阶段机）")
if (rt_dir / "requirement_review_phases.py").exists():
    import importlib.util
    sys.path.insert(0, str(rt_dir))
    try:
        spec = importlib.util.spec_from_file_location("qamaster_rr_phases",
                                                      rt_dir / "requirement_review_phases.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        err(f"runtime/requirement_review_phases.py: 加载失败 - {e}")
        mod = None
    finally:
        try:
            sys.path.remove(str(rt_dir))
        except ValueError:
            pass
    if mod is not None:
        ids = [p["id"] for p in mod.PHASES]
        if ids != list(range(0, 8)):
            err("runtime/requirement_review_phases.py: 阶段编号必须连续 0-7，实际: %s" % ids)
        gates = {p["gate"] for p in mod.PHASES}
        if not gates <= {"auto", "confirm"}:
            err("runtime/requirement_review_phases.py: 非法 gate 类型（应无 license）: %s" % gates)
        if mod.PHASE_BY_ID[4]["gate"] != "confirm":
            err("runtime/requirement_review_phases.py: Phase 4 应为 confirm（用户确认门）")
        if mod.PHASE_BY_ID[7]["gate"] != "auto":
            err("runtime/requirement_review_phases.py: Phase 7 应为 auto（末阶段自动门）")
rt_py = rt_dir / "qamaster_runtime.py"
if rt_py.exists():
    _rt_txt = rt_py.read_text(encoding="utf-8")
    if "def cmd_bootstrap" not in _rt_txt or '"bootstrap"' not in _rt_txt:
        err("runtime/qamaster_runtime.py: 缺少 bootstrap 子命令（req_id 派生协议）")
    if "def cmd_manifest" not in _rt_txt or '"manifest"' not in _rt_txt:
        err("runtime/qamaster_runtime.py: 缺少 manifest 子命令（Runtime 独占索引维护）")
# 铁律 4 护栏：模型禁止 Write/Edit MANIFEST.md（SKILL.md 不应含该权限示例）
_skill_md = ROOT / "skills" / "case-design" / "SKILL.md"
if _skill_md.exists():
    _sk_txt = _skill_md.read_text(encoding="utf-8")
    if re.search(r"(Write|Edit)\([^)]*MANIFEST\.md", _sk_txt):
        err("skills/case-design/SKILL.md: 仍含 Write/Edit MANIFEST.md 权限示例"
            "（铁律 4：MANIFEST 由 Runtime 维护，模型禁止 Write/Edit）")

# 7. README
if not (ROOT / "README.md").exists():
    err("README.md: 缺失")
else:
    _readme_txt = (ROOT / "README.md").read_text(encoding="utf-8")
    _assert_nums = [int(m) for m in re.findall(r"(\d+)\s*项断言", _readme_txt)]
    if len(set(_assert_nums)) > 1:
        err(f"README.md: 断言计数不一致 {sorted(set(_assert_nums))}"
            "（多处「N 项断言」须统一为同一数字，防改一处漏一处的漂移）")

# 8. 不应入库的产物（按 git 已跟踪文件判断）
try:
    out = subprocess.check_output(
        ["git", "ls-files"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
    )
    for f in out.splitlines():
        if "__pycache__" in f or f.endswith(".pyc"):
            kind = "__pycache__" if "__pycache__" in f else ".pyc"
            err(f"{f}: {kind} 不应入库（检查 .gitignore）")
except Exception:
    warn("git 不可用，跳过已跟踪文件检查")

# 输出
print("== qamaster 插件结构自检 ==")
for w in warnings:
    print(f"  WARN  {w}")
for e in errors:
    print(f"  FAIL  {e}")
if errors:
    print(f"\n结果：{len(errors)} 项失败，{len(warnings)} 项警告")
    sys.exit(1)
print(f"\n结果：通过（{len(warnings)} 项警告）")
