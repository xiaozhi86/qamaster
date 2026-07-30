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

# 7. README
if not (ROOT / "README.md").exists():
    err("README.md: 缺失")

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

# 9. case-design 机制守回归（闭合 plan P0-1/P0-2/P1-4）
wf = ROOT / "skills/case-design/scripts/case_design_workflow.py"
if wf.exists():
    wf_text = wf.read_text(encoding="utf-8")
    # P0-2：驱动器必须真实调用 gate8 / readback（非仅文档提及）
    if 'run_gate8(' not in wf_text or 'run_readback(' not in wf_text:
        err("case_design_workflow.py: 驱动器未调用 gate8/readback（P0-2 回归）")
    if 'phase == 8' not in wf_text or 'phase == 13' not in wf_text:
        err("case_design_workflow.py: 缺 Phase 8/13 内容门禁分支（P0-2 回归）")
    # P1-3：Phase 2-7 须要求 .phase_digest_N（非签空串）
    if ".phase_digest_" not in wf_text or "resolve_outputs" not in wf_text:
        err("case_design_workflow.py: Phase 2-7 未要求 .phase_digest 产物（P1-3 回归）")
    # P1-4：Phase 0 签名须含 REQ（动态 resolve_outputs 处理 phase 0）
    if not re.search(r"phase == 0", wf_text):
        err("case_design_workflow.py: Phase 0 outputs 未动态含 REQ（P1-4 回归）")
else:
    err("skills/case-design/scripts/case_design_workflow.py: 缺失")

# P0-1：install_hook.py 必须存在 + README 须含 hook 安装步骤
ih = ROOT / "scripts/install_hook.py"
if not ih.exists():
    err("scripts/install_hook.py: 缺失（P0-1：hook 无法在消费方安装）")
readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
if "install_hook.py" not in readme:
    err("README.md: 未提及 install_hook.py 安装步骤（P0-1 回归）")
if "步骤 4.5" not in readme and "物理强制 hook" not in readme:
    err("README.md: 未含 hook 安装步骤（P0-1 回归）")

# P2-6：preflight 须含 hook 生效自检
pf = ROOT / "skills/case-design/scripts/preflight.py"
if pf.exists():
    pf_text = pf.read_text(encoding="utf-8")
    if "check_hook_active" not in pf_text or "--check-hook" not in pf_text:
        err("preflight.py: 缺 hook 生效自检（P2-6 回归）")
else:
    err("skills/case-design/scripts/preflight.py: 缺失")

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
