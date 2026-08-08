#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
workflows/ — qamaster 通用 workflow 注册表

设计原则（R7 规避）：注册是**显式动作**，不依赖 import 副作用。
新增 skill 的状态机在此目录加 `<name>.py`，暴露 `register()` 函数，
由 `qamaster_runtime.main()` 显式调用。仅 import 该模块不会改变注册表。

每个 WorkflowSpec 自带阶段机（phases/depth_skips/knowledge_gate/last_phase），
控制器按 `--workflow` 路由取 spec，状态路径 `<workdir>/.qamaster/<workflow>/<req_id>/`
天然隔离不同 skill（同 req_id 不同 workflow 也不冲突）。
"""
