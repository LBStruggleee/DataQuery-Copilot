"""CI secret-sweep 门禁回归测试 — 收尾修复第2轮。

P1-17 引入的阻塞门禁「No tracked .env files」曾因 grep 正则
`(^|/)\\.env(\\.|$)` 把被跟踪的模板文件 `.env.example` /
`frontend/.env.example` 也判为 tracked env files（/.env 后跟
.example 的点即命中 `(\\.|$)` 分支），导致该步骤在任何含模板
文件的提交上恒 exit 1，门禁常红掩盖真回归。

修复为白名单式：主匹配后接 `grep -v -E '\\.example$'` 排除模板。
本文件以 Python re 模拟 CI 中 `grep -E ... | grep -v -E ...` 的管道
行为锁定修复——两个模式必须保持在 POSIX ERE 与 Python re 语义
一致的子集内（当前仅用锚点、分组与转义点，均兼容）。
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# 实际被 git 跟踪的模板文件（修复前正是它们触发门禁恒红）
TRACKED_EXAMPLE_FILES = [".env.example", "frontend/.env.example"]


def _sweep_step() -> str:
    """提取 ci.yml 中「No tracked .env files」步骤的 run 脚本文本。"""
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    marker = "- name: No tracked .env files"
    start = text.find(marker)
    assert start != -1, "ci.yml 中找不到 secret-sweep 的「No tracked .env files」步骤"
    end = text.find("- name:", start + len(marker))
    return text[start:end if end != -1 else len(text)]


def _sweep_patterns() -> tuple[re.Pattern, re.Pattern]:
    """从步骤脚本提取 (主匹配正则, 白名单排除正则) 并校验步骤结构。"""
    step = _sweep_step()
    assert "git ls-files" in step, "secret-sweep 步骤必须基于 git ls-files 扫描被跟踪文件"
    main = re.search(r"grep -E '([^']+)'", step)
    excl = re.search(r"grep -v -E '([^']+)'", step)
    assert main is not None, "secret-sweep 步骤缺少主匹配 grep -E 模式"
    assert excl is not None, (
        "secret-sweep 步骤缺少白名单排除 grep -v -E 模式——"
        ".env.example 属有意跟踪的模板，必须放行，否则门禁恒红（收尾修复第2轮回归）"
    )
    return re.compile(main.group(1)), re.compile(excl.group(1))


def _flagged(paths: list[str]) -> list[str]:
    """模拟 CI 管道 git ls-files | grep -E 主匹配 | grep -v -E 白名单。"""
    main_re, excl_re = _sweep_patterns()
    hits = [p for p in paths if main_re.search(p)]
    return [p for p in hits if not excl_re.search(p)]


def test_secret_sweep_passes_tracked_env_example_templates():
    """被跟踪的 .env.example 模板必须放行——修复前正则误伤导致门禁恒 exit 1。"""
    assert _flagged(TRACKED_EXAMPLE_FILES) == []


def test_secret_sweep_still_blocks_real_tracked_env_files():
    """白名单只放行 *.example 模板；真实 env 文件仍须全部被拦截。"""
    real_env_files = [".env", ".env.local", "frontend/.env", "config/.env.production"]
    assert _flagged(real_env_files) == real_env_files
    # 普通源文件不误伤；形如 .envexample（无点分隔）也不是 env 文件
    assert _flagged(["src/main.py", "README.md", "docs/technical_doc.md", ".envexample"]) == []
