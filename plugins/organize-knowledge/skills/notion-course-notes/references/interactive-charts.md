# 交互函数图表：保留源程序，嵌入原生 HTML 块

发现可点击、拖动读数、悬停、缩放、切换曲线或调整参数的图表时读取本文件。不能把交互图表自动扁平化成图片后称“原样保存”。当前 Notion 的 HTML 块支持上传 HTML 文件并在沙箱 iframe 内交互运行，优先使用该原生路径，不要求用户先公开网站。

依据：[Notion HTML blocks](https://developers.notion.com/reference/block#html-blocks)。实际执行时读取当前 `notion://docs/enhanced-markdown-spec` 和工具 schema；旧的“不支持 HTML/JavaScript、只能截图或公开外链”判断不能直接套用。

## 1. 识别真实来源与可迁移程度

- 分别盘点原交互产物和截图。优先取当前聊天真实可读的 HTML/JavaScript、图表数据、配置、公式、参数范围、默认值、单位及工具返回的文件。已有原 HTML 时保持字节不变，并计算真实 SHA-256。
- “原件”仅用于实际取得的原源文件；用户提供的 HTML 标明 `user_provided`。React/图表配置需要导出可运行 HTML 时标 `ported`（根据原源迁移），记录所做的封装；不能宣称源文件一字不改。截图推测后重建只能标 `reconstructed`，且须用户要求重建，不冒充原件。
- **只有截图不能恢复原交互程序**。截图仍按图片流程保存，交互项标“缺原始 HTML/数据/程序”，提示在产生图表的原聊天调用或提供原文件；不能从视觉上看到曲线就称已取得数据及控件。用户这类“单位脉冲响应”“温度曲线对比”截图只用于识别图表类型，不当成可执行源码。
- 盘点原来真实存在的交互：拖动时间指针、悬停读数、参数输入、滑块、缩放等。原图仅支持移动读数时，不冒称它原本能修改时间常数；若用户明确要求添加参数控制，做成标注清楚的增强版本。
- HTML 应带齐原有 CSS、JS 和数据。检查相对资源、CDN、模块导入、接口请求与对 ChatGPT 父窗口/工具运行时的依赖；这些依赖不一定能在 Notion 沙箱运行。能取得依赖时封装导出并标迁移，无法取得时保留源文件与缺口，不用空白图或截图宣称交互成功。

## 2. 私有上传并插入 Notion

1. 先执行 [重复检查](../../study-chat-notes/references/deduplication.md)。已验证相同源程序、数据、控件与默认参数时复用原 embed，不重复上传；旧笔记只有截图而缺交互块属于待补，不跳过。
2. 检查连接实际支持 `create_attachment` 和页面创建/更新。小型 UTF-8 HTML（当前内容上传上限 200 KiB）使用 `create_attachment(content=完整源码, filename=真实名称.html, content_type=text/html)`。不要把源码放进正文代码块。
3. 保留返回的真实 `file_upload_id` 和 `markdown_source`；不要自造 ID。超出内容上传限制时使用本集成的可用文件上传接口，完成上传后按其实际响应继续，不能截断 HTML 或复用图片上传逻辑时保留错误 MIME。
4. **使用原生 `<embed>` 插入**。`create_attachment` 的 `markdown_source` 作为 `src`；文件上传工具给出 `suggested_markdown` 时直接使用。当前结构是 `<embed src="实际返回的 file-upload://来源">图表标题与来源说明</embed>`，不是 `<file>`、图片块或 HTML 代码块。源引用会在保存页面时真正绑定，不是得到上传 ID 就算已经嵌入。
5. 插在对应知识点附近，复杂图表放全宽段，保留函数公式、参数/单位说明与原有正文；静态预览可补充，但不能替代交互原件。标题说明“原件/源迁移/重建”，不要把模板参考图当成学习图。
6. 回读页面，确认实际是 `<embed>`、父级正确且内容未截断；可用 `download_attachment(file_upload_id=真实值)` 回读小型 HTML 并核对源码哈希。回读可能返回临时签名 URL，不能当永久导出地址，过期后重新读取原页。

嵌入保持页面原来的访问范围，不公开 GitHub 仓库或课程页面，也不需要为此新建公开托管站点。只有原产物本来是可嵌入外链且用户允许使用时才走外链路径，并检查来源、有效性与访问条件。

## 3. 验证交互，而不只验证“有一个块”

- 有可用浏览器/预览执行能力时实际打开 HTML 和 Notion 中的 embed：测试点击/拖动读数、原有参数输入、重绘、重置等功能，核对默认状态及改变参数后的结果。每项仅在实际操作后记通过；仅出现事件处理代码不等于通过。
- 回读结构和源码哈希只能证明文件及块已保存，不能证明 JavaScript 实际运行，更不能证明 iPhone 已验证。没有 UI 执行能力时报告“HTML 已嵌入；交互运行尚未实测”，不能一律称所有功能完整保留。
- iPhone 需要触摸拖动/点按实际验证；Windows/网页的鼠标验证不能替代手机实测。Notion 沙箱、容器宽度和客户端字体可能影响显示，不承诺像素级复刻 ChatGPT 外壳。
- 参数控件改变的是图表运行时状态，修改程序逻辑仍需编辑源文件并更新 HTML。除非原程序的状态保存机制已验证，不承诺退出/刷新后自动保留每次拖动的参数。
- 区分状态：`source_missing`、`source_obtained`、`uploaded_not_embedded`、`embedded_unverified`、`interactive_verified`。原件缺失、依赖缺失或只剩静态截图时标“部分完成”，列具体缺口，继续其他已选任务。

## 4. GitHub 与 Obsidian 的原件备份

默认两处保存策略继续执行。除 Markdown 外，将实际取得的 HTML 原件/迁移产物作为关联资产保存在同课程目录，如 `assets/interactive/<真实源码SHA256>.html`，必要的数据文件也按实际内容归档。先读取已有同路径文件并比较：完全相同则跳过，路径冲突且内容不同不能覆盖。用可用 GitHub 创建 UTF-8 文件工具保存 HTML/JSON/CSS/JS；二进制依赖按实际可用工具处理，不能仅列文件名就声称已备份。

Markdown 使用实际交付的相对路径链接 HTML，保留公式、YAML 和 `related_candidates`；用户拉取/复制笔记后可在浏览器打开源文件。私有 GitHub 中的 HTML 不是可直接给 Notion 运行的网站，不能把 blob/raw 链接当 HTML 托管。标准 Markdown 或 Obsidian 代码块也不会因此自动获得这些交互。

分别验证“Notion HTML embed”“GitHub 源文件”“Markdown 引用路径”，一边重复不表示另一边已有。源文件/数据/参数或交互能力有新增时，即使文字相同也属于新增内容；保存资产和修订对应 Markdown，不被纯文字去重误跳过。用户明确只选一个目标时遵守其选择。

## 5. 可选的本地准备工具

[prepare_notion_html.py](../scripts/prepare_notion_html.py) 读取现有完整 HTML，保留 UTF-8 原文、计算哈希、列出静态资源与宿主依赖线索，为小文件生成当前 `create_attachment` 的请求参数。它不上传、不执行 JS、不重建截图，也不会把有代码误报为交互验证通过。

```sh
python prepare_notion_html.py --html actual-chart.html --title 图表标题 --origin original --source-description 实际工具产物或用户文件来源 --output chart-upload-plan.json
```

`origin` 可为 `original`、`user_provided`、`ported`、`reconstructed`，必须按事实选择。准备结果只表示本地源文件已取得，不等于已经传入 Notion。无终端时可直接用原 HTML 内容调用连接器，不能把没有 Python 当作无法处理交互图表的理由。
