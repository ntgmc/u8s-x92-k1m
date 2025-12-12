import streamlit as st
import json
import os
import datetime
import time

# ==========================================
# 版本控制与导入
# ==========================================
APP_VERSION = "1.4.1"  # App 前端版本

# 尝试从 logic 导入版本号，如果不存在则使用默认值
try:
    from logic import WorkplaceOptimizer
    from logic import VERSION as LOGIC_VERSION
except ImportError:
    # 如果 logic.py 中没有定义 VERSION 变量
    from logic import WorkplaceOptimizer

    LOGIC_VERSION = "1.0.0"
except Exception:
    # 处理其他可能的导入错误
    LOGIC_VERSION = "Unknown"

# ==========================================
# 0. 全局配置与样式优化
# ==========================================
st.set_page_config(
    page_title="MAA基建排班生成器",
    layout="wide",
    page_icon="🏭",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem;}
    h1 {font-family: 'Helvetica Neue', sans-serif; font-weight: 700;}
    .stButton>button {border-radius: 8px; font-weight: bold;}
    .stDownloadButton>button {width: 100%; border-radius: 6px;}
    /* 隐藏 Streamlit 默认菜单，看起来更像独立 App */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* ===== 强制隐藏右上角 GitHub 图标（绝对生效版） ===== */

    /* 核心按钮容器 */
    .stAppHeader .stToolbarActions .stToolbarActionButton button {
        display: none !important;
        visibility: hidden !important;
        pointer-events: none !important;
    }

    /* 为防止版本变动，连父级也一起隐藏 */
    .stAppHeader .stToolbarActions .stToolbarActionButton {
        display: none !important;
        visibility: hidden !important;
        pointer-events: none !important;
    }

    /* 某些版本中该按钮会有 data-testid：stToolbarActionButtonIcon */
    [data-testid="stToolbarActionButtonIcon"] {
        display: none !important;
        visibility: hidden !important;
        pointer-events: none !important;
    }

    /* 完全移除容器占位空间 */
    .stAppHeader .stToolbarActions {
        gap: 0 !important;
    }
    </style>
""", unsafe_allow_html=True)


def get_timestamp():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# 状态初始化
if 'calculated' not in st.session_state:
    st.session_state.calculated = False
if 'results' not in st.session_state:
    st.session_state.results = {}

# ==========================================
# 1. 侧边栏：数据源 (Source of Truth)
# ==========================================
with st.sidebar:
    # st.image("https://web.hycdn.cn/arknights/official/assets/images/brand.png", width=100)  # 只是个示例Logo，可换
    st.title("MAA基建排班生成器")

    # --- [新增] 版本显示区域 ---
    st.markdown(f"""
    <div style="
        display: flex; 
        justify-content: space-between; 
        background-color: #f0f2f6;
        padding: 8px 12px;
        border-radius: 6px;
        color: #555; 
        font-size: 0.85rem;
        font-family: monospace;
        margin-bottom: 15px;
    ">
        <span>App: v{APP_VERSION}</span>
        <span>Logic: v{LOGIC_VERSION}</span>
    </div>
    """, unsafe_allow_html=True)
    # -------------------------

    st.markdown("---")

    st.subheader("📂 数据导入")
    base_efficiency_path = "internal"

    # 使用 Tab 切换导入方式，更简洁
    import_tab1, import_tab2 = st.tabs(["📋 剪贴板 (推荐)", "📁 文件上传"])

    with import_tab1:
        pasted_ops = st.text_area(
            "粘贴 MAA 导出的 JSON",
            height=300,
            help="在 MAA '小工具' -> '干员识别' -> 识别后点击 '复制到剪贴板'，然后在此处 Ctrl+V粘贴",
            placeholder='[\n  {\n    "id": "char_002_amiya",\n    "name": "阿米娅",\n    ...\n  }\n]'
        )
        if pasted_ops:
            st.success("已检测到文本数据")

    with import_tab2:
        uploaded_ops = st.file_uploader("上传 operators.json", type="json")

    st.markdown("---")
    st.caption(f"Author: 一只摆烂的42")

# ==========================================
# 2. 主界面：分步配置向导
# ==========================================

st.markdown("## 🏭 基建排班控制台")

# 在这里创建一个空的容器，用于稍后展示进度条
status_container = st.empty()

st.markdown("根据您的干员练度与基建布局，生成理论最高效率的排班方案...")

# ==========================================
# --- 板块 1: 基建布局 (Layout) ---
# ==========================================

with st.container(border=True):
    st.subheader("1. 基建布局设定")

    # 使用列布局 + Radio 模拟预设按钮
    l_col1, l_col2 = st.columns([1, 2])

    with l_col1:
        layout_preset = st.radio(
            "⚡ 快速预设 (3发电站)",
            ["2-4-3 (均衡)", "3-3-3 (搓玉推荐)", "1-5-3 (极限制造)", "自定义"],
            index=0,
            horizontal=False
        )

    with l_col2:
        # 初始化产物默认值变量
        p_lmd, p_gold, p_rec, p_shard = 0, 0, 0, 0

        # --- 核心修改逻辑：根据预设定义建筑数量 & 产物分配默认值 ---
        if layout_preset == "3-3-3 (搓玉推荐)":
            # 3贸易 3制造 -> 2赤金 0经验 1碎片 | 2龙门币 1合成玉
            def_t, def_m = 3, 3
            p_lmd = 2  # 贸易站默认分配给龙门币的数量 (剩余给合成玉)
            p_gold = 2  # 制造站：赤金
            p_rec = 0  # 制造站：经验
            p_shard = 1  # 制造站：碎片
            disabled = True

        elif layout_preset == "2-4-3 (均衡)":
            # 2贸易 4制造 -> 2赤金 2经验 | 全龙门币
            def_t, def_m = 2, 4
            p_lmd = 2
            p_gold = 2
            p_rec = 2
            p_shard = 0
            disabled = True

        elif layout_preset == "1-5-3 (极限制造)":
            # 1贸易 5制造 -> 2赤金 3经验 | 全龙门币
            def_t, def_m = 1, 5
            p_lmd = 1
            p_gold = 2
            p_rec = 3
            p_shard = 0
            disabled = True

        else:  # 自定义
            def_t, def_m = 2, 4
            disabled = False
            # 自定义模式下，默认值设为当前输入框可能的合理值，后续由用户调整
            p_lmd = 2
            p_gold = 2
            p_rec = 2
            p_shard = 0

        c1, c2 = st.columns(2)
        # 注意：这里仅仅是布局数量
        n_trading = c1.number_input("贸易站", 0, 6, def_t, disabled=disabled)
        n_manufacture = c2.number_input("制造站", 0, 6, def_m, disabled=disabled)

        # 如果是自定义模式，需要修正一下 p_lmd 防止溢出 (比如切到自定义把贸易站降为0)
        if layout_preset == "自定义":
            p_lmd = min(p_lmd, n_trading)

        # 实时计算发电站并校验
        n_power = 9 - n_trading - n_manufacture
        if n_power != 3:
            st.warning(f"当前为 {n_power} 发电站布局。算法目前仅针对 3 发电站优化，暂不支持其他布局。",
                       icon="⚠️")
        else:
            st.caption(f"当前布局: {n_trading}贸易 - {n_manufacture}制造 - {n_power}发电")

# ==========================================
# --- 板块 2: 产物策略 (Strategy) ---
# ==========================================

with st.container(border=True):
    st.subheader("2. 产物策略分配")

    col_prod1, col_prod2 = st.columns(2)

    # 贸易站策略
    with col_prod1:
        st.markdown("#### 💰 贸易站订单")
        if n_trading > 0:
            # 滑块逻辑：使用上方计算出的 p_lmd 作为 value
            # 注意：key的设置可以帮助Streamlit在预设切换时强制刷新组件
            req_lmd = st.slider(
                "龙门币 (LMD) 占比",
                0, n_trading,
                value=p_lmd,
                help="剩下的将分配给合成玉"
            )
            req_orundum = n_trading - req_lmd

            st.info(f"分配: {req_lmd} 龙门币 + {req_orundum} 合成玉")
        else:
            req_lmd, req_orundum = 0, 0
            st.write("无贸易站")

    # 制造站策略
    with col_prod2:
        st.markdown("#### 📦 制造站产线")
        m1, m2, m3 = st.columns(3)

        # 使用上方计算出的 p_gold, p_rec, p_shard 作为 value
        req_gold = m1.number_input("赤金", 0, n_manufacture, value=p_gold)
        req_record = m2.number_input("经验书", 0, n_manufacture, value=p_rec)
        req_shard = m3.number_input("源石碎片", 0, n_manufacture, value=p_shard)

        current_m_total = req_gold + req_record + req_shard
        if current_m_total != n_manufacture:
            st.error(f"分配错误: 已分配 {current_m_total} / {n_manufacture} 间设施", icon="🚫")
        else:
            st.success(f"产线分配完成", icon="✅")

# --- 板块 3: 自动化科技 (Advanced) ---
with st.expander("⚙️ 高级设置 (菲亚梅塔 / 无人机)", expanded=False):
    col_adv1, col_adv2 = st.columns(2)

    with col_adv1:
        st.markdown("##### 🔥 菲亚梅塔体系")
        enable_fia = st.toggle("启用自动充能", value=False, help="自动识别排班中收益最高的干员进行心情恢复")
        if enable_fia:
            st.warning(
                "**重要提示**：\n\n"
                "菲亚梅塔体系需要**严格保证换班时间**（通常为 12小时 或 8小时一换）。\n"
                "建议配合 **MAA 定时任务** 或闹钟使用。\n\n"
                "🚫 **如果无法保证准时换班，充能对象极易心情耗尽（红脸），反而降低效率，此时请关闭此选项。**",
                icon="⚠️"
            )

    with col_adv2:
        st.markdown("##### 🚁 无人机加速")
        enable_drone = st.toggle("启用无人机加速", value=True)

        drone_targets = []
        if enable_drone:
            # 紧凑型选择器
            product_map = {"龙门币": "LMD", "赤金": "Pure Gold", "经验书": "Battle Record", "合成玉": "Orundum"}
            rev_map = {v: k for k, v in product_map.items()}

            dc1, dc2, dc3 = st.columns(3)
            # 默认方案
            t1 = dc1.selectbox("班次 1", list(product_map.keys()), index=0)  # LMD
            t2 = dc2.selectbox("班次 2", list(product_map.keys()), index=1)  # Gold
            t3 = dc3.selectbox("班次 3", list(product_map.keys()), index=0)  # LMD
            drone_targets = [product_map[t1], product_map[t2], product_map[t3]]

        drone_order = "pre"

# ==========================================
# 3. 核心执行与状态反馈
# ==========================================
st.markdown("---")
col_action, col_blank = st.columns([1, 2])

# 构建 Config
current_config = {
    "product_requirements": {
        "trading_stations": {"LMD": req_lmd, "Orundum": req_orundum},
        "manufacturing_stations": {"Pure Gold": req_gold, "Originium Shard": req_shard, "Battle Record": req_record}
    },
    "trading_stations_count": n_trading,
    "manufacturing_stations_count": n_manufacture,
    "Fiammetta": {"enable": enable_fia},
    "drones": {"enable": enable_drone, "order": drone_order, "targets": drone_targets}
}

# 校验逻辑
is_config_valid = (current_m_total == n_manufacture) and ((req_lmd + req_orundum) == n_trading)
is_data_ready = (pasted_ops is not None and pasted_ops.strip() != "") or (uploaded_ops is not None)

if col_action.button("🚀 生成排班方案", type="primary", use_container_width=True,
                     disabled=not (is_config_valid and is_data_ready)):

    # 准备数据源
    operators_bytes = None
    if uploaded_ops:
        operators_bytes = uploaded_ops.getvalue()
    elif pasted_ops:
        try:
            json.loads(pasted_ops)  # 简单校验
            operators_bytes = pasted_ops.encode('utf-8')
        except:
            st.toast("❌ 粘贴的 JSON 格式无效", icon="🚫")
            st.stop()

    # --- 核心修改：指定在顶部的容器中渲染 ---
    with status_container:
        # 这里的代码和之前一样，但现在它会出现在页面顶部！
        with st.status("正在启动神经模拟环境...", expanded=True) as status:
            # 初始化进度条
            progress_bar = st.progress(0)

            try:
                # --- 阶段 1: 数据加载 (10%) ---
                st.write("📥 读取干员练度数据...")
                time.sleep(0.3)  # 模拟I/O延迟

                with open("temp_ops.json", "wb") as f:
                    f.write(operators_bytes)

                progress_bar.progress(10)

                # --- 阶段 2: 配置解析 (25%) ---
                st.write("⚙️ 解析基建布局配置...")
                time.sleep(0.4)

                with open("temp_conf.json", "w", encoding='utf-8') as f:
                    json.dump(current_config, f, ensure_ascii=False)

                progress_bar.progress(25)

                # --- 阶段 3: 算法初始化 (40%) ---
                st.write("🧠 加载 WorkplaceOptimizer 核心算法...")
                # 模拟加载大型模型的延迟
                time.sleep(0.6)
                optimizer = WorkplaceOptimizer(base_efficiency_path, "temp_ops.json", "temp_conf.json")

                progress_bar.progress(40)

                # --- 阶段 4: 计算当前最优解 (65%) ---
                st.write("📊 正在演算当前练度最优解 (Monte Carlo / Greedy)...")
                time.sleep(0.8)  # 模拟复杂计算
                curr = optimizer.get_optimal_assignments(ignore_elite=False)

                progress_bar.progress(65)

                # --- 阶段 5: 计算理论极限 (85%) ---
                st.write("🔮 正在推演理论极限模型...")
                time.sleep(0.5)
                pot = optimizer.get_optimal_assignments(ignore_elite=True)

                progress_bar.progress(85)

                # --- 阶段 6: 差异分析与报告生成 (95%) ---
                st.write("📈 生成练度提升路径分析报告...")
                upgrades = optimizer.calculate_upgrade_requirements(curr, pot)


                # 结果处理逻辑
                def clean(d):
                    return {k: v for k, v in d.items() if k != 'raw_results'}


                # 生成 TXT 内容
                txt = "=== 基建提升建议 ===\n"
                txt += f"生成时间: {get_timestamp()}\n{'=' * 40}\n\n"
                if not upgrades:
                    txt += "✅ 完美！您的队伍已达到当前配置的理论极限效率。\n"
                else:
                    for item in upgrades:
                        g = item['gain']
                        g_str = f"{g * 100:.1f}%" if g < 0.9 else f"{g:.1f}%"
                        if item.get('type') == 'bundle':
                            names = "+".join([o['name'] for o in item['ops']])
                            txt += f"[组合] {names}\n   收益: {item['rooms']} 效率 +{g_str}\n"
                            for o in item['ops']: txt += f"   - {o['name']}: 精{o['current']} -> 精{o['target']}\n"
                        else:
                            txt += f"[单人] {item['name']}\n   收益: {item['rooms']} 效率 +{g_str}\n"
                            txt += f"   - 当前: 精{item['current']} -> 目标: 精{item['target']}\n"
                        txt += "-" * 30 + "\n"

                time.sleep(0.4)  # 给人一种正在“生成文件”的感觉
                progress_bar.progress(95)

                # 保存到 Session State
                st.session_state.results = {
                    "curr": json.dumps(clean(curr), ensure_ascii=False, indent=2),
                    "pot": json.dumps(clean(pot), ensure_ascii=False, indent=2),
                    "txt": txt,
                    "eff": curr['raw_results'][0].total_efficiency if curr['raw_results'] else 0
                }
                st.session_state.calculated = True

                # 清理临时文件
                if os.path.exists("temp_ops.json"): os.remove("temp_ops.json")
                if os.path.exists("temp_conf.json"): os.remove("temp_conf.json")

                # --- 完成 (100%) ---
                progress_bar.progress(100)
                time.sleep(0.2)  # 稍微停顿一下让用户看到100%
                status.update(label="✅ 神经模拟完成！方案已生成", state="complete", expanded=False)

                # 可选：给用户看1秒完成状态，然后清空顶部区域，
                # 这样用户的注意力会自然转移到下方出现的“结果仪表盘”
                # time.sleep(1.5)
                # status_container.empty()

            except Exception as e:
                status.update(label="❌ 计算过程中断", state="error")
                st.error(f"错误详情: {str(e)}")
                import traceback

                st.code(traceback.format_exc())

# ==========================================
# 4. 结果仪表盘
# ==========================================
if st.session_state.calculated:
    res = st.session_state.results

    st.markdown("### 📊 分析报告")

    # 关键指标展示
    m1, m2, m3 = st.columns(3)
    m1.metric("首班总效率", f"{res['eff']:.2f}%", delta="当前练度")
    m2.metric("排班方案", "3班轮换", help="固定为3班倒模式")
    m3.metric("基建类型", f"{n_trading}{n_manufacture}{9 - n_trading - n_manufacture}")

    st.markdown("#### 📥 方案下载")

    # 下载区使用卡片式布局
    d1, d2, d3 = st.columns(3)

    with d1:
        with st.container(border=True):
            st.markdown("**📄 当前方案**")
            st.caption("基于您现有的干员练度")
            st.download_button("下载 JSON", res['curr'], "current.json", "application/json", use_container_width=True)

    with d2:
        with st.container(border=True):
            st.markdown("**🔮 极限方案**")
            st.caption("忽略练度限制的理论最优")
            st.download_button("下载 JSON", res['pot'], "potential.json", "application/json", use_container_width=True)

    with d3:
        with st.container(border=True):
            st.markdown("**📈 提升建议**")
            st.caption("性价比最高的练度提升路径")
            st.download_button("下载 报告", res['txt'], "suggestions.txt", "text/plain", use_container_width=True)

    # 底部指南
    st.info("""
    **💡 如何使用导出的 JSON？**
    1. **自动化**: **基建换班** -> 启用 **自定义排班** -> 选择文件。
    2. **可视化**: 前往 [**一图流工具**](https://ark.yituliu.cn/tools/scheduleV2) 导入文件预览排班详情。
    """)