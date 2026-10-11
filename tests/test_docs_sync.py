"""文档测试计数一致性 — 收尾修复第2轮。

P1-12（文档同步批次）建立了「README 用例数 = pytest 实际收集数」的状态；
收尾第1轮新增 4 个测试（249 passed）后未同步文档数字，README.md 两处与
docs/v1_contract_proposal.md 一处仍写「245」，状态回归。本测试以
`pytest --collect-only` 的实测收集数为唯一事实源，锁定文档中所有后端
用例数声明，防止再次漂移。

注意：新增测试会改变收集数——补测试的提交必须同步更新文档数字，
本测试会在数字不一致时失败并给出两侧数值。
"""
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
CONTRACT_DOC = REPO_ROOT / "docs" / "v1_contract_proposal.md"


def _collected_test_count() -> int:
    """用 pytest --collect-only 实测当前测试收集数。"""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=120,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, f"pytest --collect-only 运行失败:\n{output[-2000:]}"
    m = re.search(r"(\d+) tests? collected", output)
    assert m is not None, f"无法从 collect-only 输出解析收集数:\n{output[-2000:]}"
    return int(m.group(1))


def test_documented_backend_test_count_matches_collection():
    """README 与契约文档中的后端用例数声明必须等于 pytest 实测收集数。"""
    actual = _collected_test_count()

    # README.md：「pytest，N 个用例」/「pytest，N 个测试用例」（P1-12 建立的数字=实际）
    readme_text = README.read_text(encoding="utf-8")
    readme_claims = [int(n) for n in re.findall(r"pytest，(\d+) 个(?:测试)?用例", readme_text)]
    assert readme_claims, "README.md 中未找到「pytest，N 个用例」声明，请恢复或更新该行"
    stale_readme = [(n, actual) for n in readme_claims if n != actual]
    assert not stale_readme, (
        f"README.md 用例数声明与实测不符（声明 != pytest 实测收集数）: {stale_readme}；"
        f"请运行 python -m pytest tests/ --collect-only -q 以实测数为准同步文档"
    )

    # docs/v1_contract_proposal.md：「现有 N 个后端用例」
    contract_text = CONTRACT_DOC.read_text(encoding="utf-8")
    contract_claims = [int(n) for n in re.findall(r"现有 (\d+) 个后端用例", contract_text)]
    assert contract_claims, "docs/v1_contract_proposal.md 中未找到「现有 N 个后端用例」声明"
    stale_contract = [(n, actual) for n in contract_claims if n != actual]
    assert not stale_contract, (
        f"docs/v1_contract_proposal.md 用例数声明与实测不符: {stale_contract}；"
        f"实测收集数为 {actual}"
    )
