#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
install_hook.py — 把 case-design 的 PreToolUse hook 装进当前项目

为什么需要这个脚本：
  qamaster 插件随仓库附带 `.claude/hooks/case_design_gate.py` 与
  `.claude/settings.json`（含 PreToolUse 配置），但 Claude Code **不会**自动把
  插件自带的 `.claude/settings.json` hooks 合并进你当前的项目。结果：在消费方
  项目里 v0.7.x 宣称的「harness 物理强制」hook 根本不触发，门禁降级为「模型自觉」
  的软门禁（详见 plan P0-1）。

  本脚本把 hook 脚本拷进 `<cwd>/.claude/hooks/`，并把 PreToolUse 配置**幂等合并**
  进 `<cwd>/.claude/settings.json`，让物理强制在消费方项目真正生效。

用法（在你要跑 case-design 的项目根目录执行）：
  python <插件路径>/scripts/install_hook.py
  python <插件路径>/scripts/install_hook.py --verify     # 只检查是否已装，不改文件
  python <插件路径>/scripts/install_hook.py --force      # 覆盖已存在的 hook 脚本

纯 Python 标准库，跨平台。
"""
import sys
import os
import json
import shutil
import filecmp

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 脚本位于 <repo>/scripts/install_hook.py，hook 源在 <repo>/.claude/hooks/case_design_gate.py
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
SRC_HOOK = os.path.join(REPO_ROOT, ".claude", "hooks", "case_design_gate.py")

HOOK_REL = ".claude/hooks/case_design_gate.py"
SETTINGS_REL = ".claude/settings.json"

# 要合并进项目 settings.json 的 PreToolUse 配置块
PRETOOLUSE_MATCHER = "Write|Edit|MultiEdit"
HOOK_COMMAND = "python .claude/hooks/case_design_gate.py"


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _settings_has_hook(settings):
    """项目 settings.json 是否已含本 hook 的 PreToolUse 条目。"""
    hooks = settings.get("hooks", {}) if isinstance(settings, dict) else {}
    ptu = hooks.get("PreToolUse", [])
    if not isinstance(ptu, list):
        ptu = [ptu]
    for entry in ptu:
        if not isinstance(entry, dict):
            continue
        if entry.get("matcher") != PRETOOLUSE_MATCHER:
            continue
        for h in entry.get("hooks", []) or []:
            if isinstance(h, dict) and HOOK_COMMAND in (h.get("command") or ""):
                return True
    return False


def _merge_hook_into_settings(settings):
    """幂等合并 PreToolUse 配置进 settings dict（原地改 + 返回）。"""
    if not isinstance(settings, dict) or not settings:
        settings = {}
    hooks = settings.setdefault("hooks", {})
    ptu = hooks.setdefault("PreToolUse", [])
    if not isinstance(ptu, list):
        ptu = [ptu]
        hooks["PreToolUse"] = ptu
    # 找已有同 matcher 块
    target_entry = None
    for entry in ptu:
        if isinstance(entry, dict) and entry.get("matcher") == PRETOOLUSE_MATCHER:
            target_entry = entry
            break
    if target_entry is None:
        target_entry = {"matcher": PRETOOLUSE_MATCHER, "hooks": []}
        ptu.append(target_entry)
    hs = target_entry.setdefault("hooks", [])
    if not isinstance(hs, list):
        hs = [hs]
        target_entry["hooks"] = hs
    # 幂等：已含同 command 则不加
    already = any(
        isinstance(h, dict) and HOOK_COMMAND in (h.get("command") or "")
        for h in hs
    )
    if not already:
        hs.append({"type": "command", "command": HOOK_COMMAND})
    return settings


def install(force=False):
    if not os.path.exists(SRC_HOOK):
        print("[install_hook] ❌ 找不到 hook 源：%s" % SRC_HOOK)
        print("[install_hook] 请确认在 qamaster 仓库（或已安装的插件目录）内运行。")
        return 1

    cwd = os.getcwd()
    dst_hook = os.path.join(cwd, HOOK_REL)
    dst_settings = os.path.join(cwd, SETTINGS_REL)

    # 1. 拷 hook 脚本
    hook_exists = os.path.exists(dst_hook)
    if hook_exists and not force:
        same = filecmp.cmp(SRC_HOOK, dst_hook, shallow=False)
        if same:
            print("[install_hook] ✓ hook 脚本已存在且一致：%s" % HOOK_REL)
        else:
            print("[install_hook] ⚠ hook 脚本已存在但与源不同（加 --force 覆盖）：%s" % HOOK_REL)
    else:
        os.makedirs(os.path.dirname(dst_hook), exist_ok=True)
        shutil.copy2(SRC_HOOK, dst_hook)
        print("[install_hook] ✓ 已拷贝 hook 脚本：%s" % HOOK_REL)

    # 2. 合并 settings.json
    settings = _read_json(dst_settings, {})
    if _settings_has_hook(settings):
        print("[install_hook] ✓ PreToolUse 配置已存在于：%s" % SETTINGS_REL)
    else:
        settings = _merge_hook_into_settings(settings)
        _write_json(dst_settings, settings)
        print("[install_hook] ✓ 已合并 PreToolUse 配置到：%s" % SETTINGS_REL)

    # 3. 自检报告
    print()
    print("[install_hook] === 自检 ===")
    ok_hook = os.path.exists(dst_hook)
    ok_settings = _settings_has_hook(_read_json(dst_settings, {}))
    print("  hook 脚本   : %s" % ("✓ 存在" if ok_hook else "✗ 缺失"))
    print("  settings   : %s" % ("✓ 含 PreToolUse" if ok_settings else "✗ 缺失"))
    if ok_hook and ok_settings:
        print()
        print("[install_hook] ✅ hook 已在当前项目生效。新会话后 PreToolUse 物理强制即启用。")
        print("[install_hook] 提示：Claude Code 的 hook 配置需新开会话才会加载。")
        return 0
    else:
        print()
        print("[install_hook] ❌ 安装不完整，请检查上方输出。")
        return 1


def verify():
    cwd = os.getcwd()
    dst_hook = os.path.join(cwd, HOOK_REL)
    dst_settings = os.path.join(cwd, SETTINGS_REL)
    print("[install_hook] === verify（当前项目：%s）===" % cwd)
    ok_hook = os.path.exists(dst_hook)
    ok_settings = _settings_has_hook(_read_json(dst_settings, {}))
    print("  hook 脚本   %s : %s" % (HOOK_REL, "✓" if ok_hook else "✗ 缺失"))
    print("  settings   %s : %s" % (SETTINGS_REL, "✓ 含 PreToolUse" if ok_settings else "✗ 缺失"))
    if ok_hook and ok_settings:
        print("  → 物理强制 hook 已生效")
        return 0
    print("  → hook 未生效（软门禁）。运行 install_hook.py 安装。")
    return 1


def main():
    args = sys.argv[1:]
    if "--verify" in args:
        return verify()
    force = "--force" in args
    return install(force=force)


if __name__ == "__main__":
    sys.exit(main())
