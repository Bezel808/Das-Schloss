# 中英文界面

首页和档案页提供 English / 中文 按钮。默认中文；选择后仅将 `zh` 或 `en` 保存在当前标签页的 `sessionStorage`，刷新沿用。浏览器禁用存储时仍能在当前页面切换。此存储不包含 API Key、论文或分析内容。

界面层采用本地英文词表 `static/locales/en.js`，不请求翻译服务或语言模型。`static/i18n.js` 维护文本节点与可访问属性的原始中文，通过 MutationObserver 处理既有命令式渲染器后续写入的文字。数字插值使用消息规则，固定说明使用整段翻译。切换恢复原文后再应用目标语言，不重新获取数据、创建图节点或修改输入值、选项值和数据属性。仅监听文字、节点增删及相关文字属性，不监听图谱逐帧位置变化。

作者姓名、机构、主题、论文标题与摘要通过 `translate="no"`、来源文本容器及节点名称保护保留原文。含人名的图谱提示按来源名称分段保护。证据按钮被复制到其他面板时使用原始标签，确保切回中文可恢复。JSON 数据与审计记录保持原始内容；SVG 导出采用当前界面的语言和样式。

新增界面文案需要补入英文词表。未知文案保持原文以免掩盖数据源错误；`i18n.missing` 记录本页面未覆盖的文本片段供回归检查，不对用户显示诊断噪声。不得把研究者内容写入通用翻译词表。

验证命令：

```sh
PYTHONPATH=. .venv/bin/python tests/browser_i18n.py
PYTHONPATH=. .venv/bin/python tests/browser_simple_ui.py
PYTHONPATH=. .venv/bin/python tests/browser_search_pagination.py
PYTHONPATH=. .venv/bin/python tests/browser_group_completion.py
```

双语浏览器回归覆盖：初始语言、首页切换、刷新恢复、动态搜索与档案、时间轴和图说明、团队与实验结果、切换不产生接口请求、不重建图节点、筛选保留、与界面词汇相同的中文机构和论文原文保护、JSON 原文保留、延迟错误响应、键盘操作与手机宽度。
