"""
Phase 0 环境初始化脚本
自动检查依赖、安装缺失包、验证关键路径
"""
import sys
import os
import subprocess
from pathlib import Path


def check_python_version() -> bool:
    """检查 Python 版本 >= 3.11"""
    major, minor = sys.version_info.major, sys.version_info.minor
    ok = major > 3 or (major == 3 and minor >= 11)
    print(f"{'✅' if ok else '❌'} Python {major}.{minor} {'✓' if ok else '需要 >= 3.11'}")
    return ok


def check_node_version() -> bool:
    """检查 Node.js 版本 >= 18"""
    try:
        result = subprocess.run(
            ["node", "--version"], capture_output=True, text=True
        )
        version_str = result.stdout.strip().lstrip("v")
        major = int(version_str.split(".")[0])
        ok = major >= 18
        print(f"{'✅' if ok else '❌'} Node.js {version_str} {'✓' if ok else '需要 >= 18'}")
        return ok
    except FileNotFoundError:
        print("❌ Node.js 未安装")
        return False


def install_python_deps() -> bool:
    """安装 Python 依赖"""
    requirements = Path(__file__).parent.parent.parent / "src" / "agents" / "requirements.txt"
    if not requirements.exists():
        print("❌ requirements.txt 不存在")
        return False

    print("📦 安装 Python 依赖...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements)],
            check=True,
            capture_output=True
        )
        print("✅ Python 依赖安装完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Python 依赖安装失败: {e}")
        return False


def install_node_deps() -> bool:
    """安装 Node.js 依赖"""
    print("📦 安装 Node.js 依赖...")
    try:
        subprocess.run(
            ["npm", "install", "--prefix", str(Path(__file__).parent.parent)],
            check=True,
            capture_output=True
        )
        print("✅ Node.js 依赖安装完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Node.js 依赖安装失败: {e}")
        return False


def verify_modules() -> bool:
    """验证核心模块可导入"""
    checks = [
        ("ezdxf", "cad_tools"),
        ("chromadb", "rag_tools"),
        ("langgraph", "graph"),
    ]
    all_ok = True
    for module, _ in checks:
        try:
            __import__(module)
            print(f"✅ {module} 可用")
        except ImportError:
            print(f"❌ {module} 未安装")
            all_ok = False
    return all_ok


def main():
    print("=" * 50)
    print("AI-CAD 环境初始化")
    print("=" * 50)

    checks = [
        check_python_version(),
        check_node_version(),
    ]

    if not all(checks):
        print("\n⚠️  前置检查未通过，请安装必要工具后重试")
        sys.exit(1)

    deps_ok = install_python_deps() and install_node_deps()
    verify_ok = verify_modules() if deps_ok else False

    if deps_ok and verify_ok:
        print("\n✅ 环境初始化完成，可以开始开发")
    else:
        print("\n⚠️  部分依赖检查失败，请查看上方输出")
        sys.exit(1)


if __name__ == "__main__":
    main()
