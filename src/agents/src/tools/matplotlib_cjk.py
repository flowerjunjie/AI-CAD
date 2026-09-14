"""matplotlib 中文渲染收敛点 — 让所有图上的汉字不再变豆腐块。

根因: matplotlib 默认走 DejaVu Sans, 无 CJK 字形, 中文标题/标注全乱码。
系统里其实装了 SimHei / Microsoft YaHei / SimSun, 只是 matplotlib 没选它们。

用法: 任何"往 matplotlib 图上画中文"的入口, import 后调一次 configure_cjk():

    from src.agents.src.tools.matplotlib_cjk import configure_cjk
    configure_cjk()          # 幂等, 反复调无副作用

设计取舍: 单一收敛点, 两个渲染入口 (run.py 预览 / render_floorplan.py 户型图)
都引它 — 一个问题进来, 一类问题出去, 不在每个文件里各配一遍。
"""
import logging

_configured = False

# 按优先级排序: 越靠前越优先。Windows 上 Microsoft YaHei 最全, 兜底 SimHei/SimSun。
_CJK_CANDIDATES = [
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
    "PingFang SC",
]


def _pick_cjk_font():
    """从已安装字体里挑一个可用的 CJK 字体, 挑不到返回 None。"""
    from matplotlib import font_manager
    available = {f.name for f in font_manager.fontManager.ttflist}
    for cand in _CJK_CANDIDATES:
        if cand in available:
            return cand
    return None


def configure_cjk() -> str | None:
    """让 matplotlib 用上 CJK 字体。幂等。返回实际选中的字体名, 没有 CJK 字体返回 None。"""
    global _configured
    if _configured:
        return None

    import matplotlib

    font = _pick_cjk_font()
    rc = matplotlib.rcParams
    rc["axes.unicode_minus"] = False  # 负号显示, 否则中文环境下负号也变方块

    if font:
        rc["font.sans-serif"] = [font] + _CJK_CANDIDATES
        rc["font.family"] = "sans-serif"
        logging.info("matplotlib CJK 字体已配置: %s", font)
    else:
        logging.warning("未找到任何 CJK 字体, 中文标题仍可能乱码 (需安装 SimHei/雅黑)")

    _configured = True
    return font
