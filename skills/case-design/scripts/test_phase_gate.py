#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_phase_gate.py — Phase 0-7 前置门禁自动化测试

测试场景：
1. 跳过 Phase 0-1，直接执行 gate8 → 应拒绝
2. 只有 MANIFEST.md，没有 Clarification_Ledger → 应拒绝
3. MANIFEST.md 和 Clarification_Ledger 都存在 → 应通过前置检查
4. 阶段签名机制 → 应正确写入和验证

用法：
    python test_phase_gate.py
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess

# 设置 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# 添加 scripts 目录到路径
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), 'scripts')
sys.path.insert(0, SCRIPTS_DIR)

# 测试目录
TEST_DIR = None

def setup_test_env():
    """创建测试环境"""
    global TEST_DIR
    TEST_DIR = tempfile.mkdtemp(prefix="test_phase_gate_")
    print(f"[Setup] 测试目录: {TEST_DIR}")

    # 创建 case-design-out 目录
    out_dir = os.path.join(TEST_DIR, "case-design-out")
    os.makedirs(out_dir, exist_ok=True)

    # 创建测试用例文件
    tc_file = os.path.join(TEST_DIR, "test_tc.md")
    with open(tc_file, 'w', encoding='utf-8') as f:
        f.write("""| 用例ID | 用例名称 | 测试类型 | 测试维度 | 优先级 | 前置条件 | 测试步骤 | 预期结果 | 关联需求ID | 关联规则 | edit_mode | tag | owner | status | 备注 |
|--------|---------|---------|---------|--------|---------|---------|---------|-----------|---------|-----------|-----|-------|--------|-----|
| TC001 | 用户登录成功 | 功能测试 | 输入验证 | P1 | 用户已注册 | 1.输入用户名 2.输入密码 3.点击登录 | 登录成功跳转首页 | REQ001 | R1 | STEP | AI | AI | Completed | |
""")
    return TEST_DIR


def cleanup_test_env():
    """清理测试环境"""
    global TEST_DIR
    if TEST_DIR and os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
        print(f"[Cleanup] 已删除测试目录: {TEST_DIR}")


def run_gate8(tc_file):
    """运行 gate8 命令"""
    cmd = [
        sys.executable,
        os.path.join(SCRIPTS_DIR, 'run_phase.py'),
        'gate8',
        tc_file
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=TEST_DIR,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=10
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def test_1_skip_phase_0_and_1():
    """测试场景1：跳过 Phase 0-1，直接执行 gate8"""
    print("\n" + "="*60)
    print("Test Scenario 1: Skip Phase 0-1, execute gate8 directly")
    print("="*60)

    # 不创建 MANIFEST.md
    # 不创建 Clarification_Ledger_*.md
    tc_file = os.path.join(TEST_DIR, "test_tc.md")

    exit_code, stdout, stderr = run_gate8(tc_file)

    # 验证结果
    print(f"\n[Result] Exit Code: {exit_code}")
    print(f"[Output] {stdout[:200]}...")

    # 断言：exit_code 应该非 0（失败）
    assert exit_code != 0, f"Should return non-zero exit code, got {exit_code}"
    assert "MANIFEST_MISSING" in stdout, "Should contain MANIFEST_MISSING error"

    print("[PASS] Test passed: gate8 correctly rejected execution (missing MANIFEST.md)")
    return True


def test_2_only_manifest():
    """测试场景2：只有 MANIFEST.md，没有 Clarification_Ledger"""
    print("\n" + "="*60)
    print("Test Scenario 2: Only MANIFEST.md, no Clarification_Ledger")
    print("="*60)

    # 创建 MANIFEST.md
    out_dir = os.path.join(TEST_DIR, "case-design-out")
    manifest_file = os.path.join(out_dir, "MANIFEST.md")
    with open(manifest_file, 'w', encoding='utf-8') as f:
        f.write("""| 需求标识 | 需求名称 | 需求文档 | 澄清台账 | 测试用例 | 知识总结 | 状态 | 备注 |
|---------|---------|---------|---------|---------|---------|------|------|
| REQ001 | 用户登录 | REQ_001.md | Clarification_Ledger_001.md | TestCases_001.md | Knowledge_001.md | 进行中 | |
""")

    tc_file = os.path.join(TEST_DIR, "test_tc.md")
    exit_code, stdout, stderr = run_gate8(tc_file)

    # 验证结果
    print(f"\n[Result] Exit Code: {exit_code}")
    print(f"[Output] {stdout[:200]}...")

    # 断言：exit_code 应该非 0（失败）
    assert exit_code != 0, f"Should return non-zero exit code, got {exit_code}"
    assert "CLARIFICATION_MISSING" in stdout, "Should contain CLARIFICATION_MISSING error"

    print("[PASS] Test passed: gate8 correctly rejected execution (missing Clarification_Ledger)")
    return True


def test_3_all_prerequisites():
    """测试场景3：MANIFEST.md 和 Clarification_Ledger 都存在"""
    print("\n" + "="*60)
    print("Test Scenario 3: Both MANIFEST.md and Clarification_Ledger exist")
    print("="*60)

    # MANIFEST.md 已在场景2创建

    # 创建 Clarification_Ledger_001.md
    out_dir = os.path.join(TEST_DIR, "case-design-out")
    ledger_file = os.path.join(out_dir, "Clarification_Ledger_001.md")
    with open(ledger_file, 'w', encoding='utf-8') as f:
        f.write("""# 澄清台账

## 需求标识
REQ001 - 用户登录

## 待确认问题
暂无

## 假设清单
暂无
""")

    tc_file = os.path.join(TEST_DIR, "test_tc.md")
    exit_code, stdout, stderr = run_gate8(tc_file)

    # 验证结果
    print(f"\n[Result] Exit Code: {exit_code}")
    print(f"[Output] {stdout[:300]}...")

    # 断言：前置检查应该通过，但测试用例内容可能不合格
    # 关键是不应该出现 MANIFEST_MISSING 或 CLARIFICATION_MISSING
    assert "MANIFEST_MISSING" not in stdout, "Should not have MANIFEST_MISSING error"
    assert "CLARIFICATION_MISSING" not in stdout, "Should not have CLARIFICATION_MISSING error"

    print("[PASS] Test passed: gate8 pre-check passed (both MANIFEST.md and Clarification_Ledger exist)")
    return True


def test_4_phase_signature():
    """测试场景4：阶段签名机制"""
    print("\n" + "="*60)
    print("Test Scenario 4: Phase signature mechanism")
    print("="*60)

    # 运行 gate-phase 命令
    cmd = [
        sys.executable,
        os.path.join(SCRIPTS_DIR, 'run_phase.py'),
        'gate-phase',
        '0',
        'MANIFEST.md'
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=TEST_DIR,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=10
        )

        print(f"\n[Result] Exit Code: {result.returncode}")
        print(f"[Output] {result.stdout}")

        # 检查签名文件是否创建
        sig_file = os.path.join(TEST_DIR, "case-design-out", ".phase_signatures.json")
        if os.path.exists(sig_file):
            with open(sig_file, 'r', encoding='utf-8') as f:
                sig_data = json.load(f)

            print(f"[Signature File] {json.dumps(sig_data, ensure_ascii=False, indent=2)}")

            # 验证签名内容
            assert "phases" in sig_data, "Signature file should contain 'phases' field"
            assert "0" in sig_data["phases"], "Signature file should contain Phase 0 signature"
            assert sig_data["phases"]["0"]["completed"] == True, "Phase 0 should be marked as completed"

            print("[PASS] Test passed: Phase signature mechanism works correctly")
            return True
        else:
            print("[WARN] Signature file not created (possibly test environment issue)")
            return False

    except Exception as e:
        print(f"[WARN] Test failed: {e}")
        return False


def main():
    """运行所有测试"""
    print("="*60)
    print("Phase 0-7 Pre-phase Gate Automated Tests")
    print("="*60)

    try:
        # 创建测试环境
        setup_test_env()

        # 运行测试
        results = []
        results.append(("Test Scenario 1", test_1_skip_phase_0_and_1()))
        results.append(("Test Scenario 2", test_2_only_manifest()))
        results.append(("Test Scenario 3", test_3_all_prerequisites()))
        results.append(("Test Scenario 4", test_4_phase_signature()))

        # 打印总结
        print("\n" + "="*60)
        print("Test Summary")
        print("="*60)
        for name, result in results:
            status = "[PASS]" if result else "[FAIL]"
            print(f"{name}: {status}")

        # 统计
        passed = sum(1 for _, r in results if r)
        total = len(results)
        print(f"\nTotal: {passed}/{total} passed")

        if passed == total:
            print("\n[SUCCESS] All tests passed!")
            return 0
        else:
            print("\n[WARNING] Some tests failed")
            return 1

    except AssertionError as e:
        print(f"\n[ERROR] Test assertion failed: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Test exception: {e}")
        return 1
    finally:
        # 清理测试环境
        cleanup_test_env()


if __name__ == "__main__":
    sys.exit(main())