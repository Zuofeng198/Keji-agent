"""科吉 CLI 工具调度器 —— 每个工具调用启动独立进程执行

用法:
    python cli.py <tool_name> <json_args>

示例:
    python cli.py get_time "{}"
    python cli.py create_document "{\"title\":\"报告\",\"count\":10}"

输出 (stdout):  JSON {"ok": true, "result": "..."}  或  {"ok": false, "error": "..."}
退出码:          0 = 成功, 1 = 失败
"""

import json
import sys
import os
import logging

# 修复 Windows GBK 编码无法输出 emoji/中文的问题
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 抑制工具注册日志：CLI stdout 必须只包含结果 JSON，不能混入日志行
logging.getLogger('keji').setLevel(logging.ERROR)

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.tools import _tool_registry  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "用法: python cli.py <tool_name> <json_args>"}))
        sys.exit(1)

    tool_name = sys.argv[1]

    # 解析 JSON 参数
    args = {}
    if len(sys.argv) >= 3:
        try:
            args = json.loads(sys.argv[2])
        except json.JSONDecodeError as e:
            print(json.dumps({"ok": False, "error": f"参数 JSON 解析失败: {e}"}))
            sys.exit(1)

    # 转换列表参数为命名参数（与 _exec_one 逻辑一致）
    meta = _tool_registry.get(tool_name)
    if meta is None:
        print(json.dumps({"ok": False, "error": f"工具不存在: {tool_name}"}, ensure_ascii=False))
        sys.exit(1)

    if isinstance(args, list):
        param_names = list(meta["parameters"].keys())
        mapped = {}
        for i, v in enumerate(args):
            if i < len(param_names):
                mapped[param_names[i]] = v
            else:
                mapped[f"arg{i}"] = v
        args = mapped

    # 执行工具
    try:
        result = meta["func"](**args)
        # 强制刷新，确保结果 JSON 是 stdout 最后一行
        sys.stdout.flush()
        print(json.dumps({"ok": True, "result": str(result)}, ensure_ascii=False), flush=True)
        sys.exit(0)
    except Exception as e:
        sys.stdout.flush()
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
