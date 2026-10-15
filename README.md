# Organize knowledge

把学习聊天整理为完整的 **Notion 课程笔记**和适合关联的 **Obsidian Markdown**。

Organize knowledge 是一套可重复使用的 Skills 和插件源码。它从当前实际可读取的聊天中提取概念、公式、推导、例题、操作步骤、追问和纠错，按课程归类；同时处理可访问的用户图片和助手配图，并为手机阅读整理公式字号和计算段落。

**当前版本：0.1.4 · MIT 开源许可 · 以中文学习笔记为主。**

## 能做什么

- **完整整理知识**：合并重复讲解，保留独立知识点、条件、推导和完整例题，不用简短摘要替代正文。
- **保存 Notion 笔记**：在使用者指定的课程位置创建笔记，包含目录、重点、公式、例题、易错点和复习问题。
- **归档图片**：处理可读取的用户图片、助手生成图、实物配图及图片卡片；执行上传、插入、回读核对，并单独报告缺图。
- **手机公式排版**：估算公式宽度，选择合适字号；长式必要时分行；代入、结果、判断与最终取值分别成块。
- **导出 Obsidian Markdown**：按概念独立组织，提供建议文件名、别名、标签和候选关联，直接在聊天中输出以便复制。

## 三个 Skills

- `study-chat-notes`：完整流程，一次交付 Notion 与 Obsidian 两种笔记。
- `notion-course-notes`：只整理并保存 Notion 课程学术笔记。
- `obsidian-concept-notes`：只输出可复制的 Obsidian 概念笔记，默认由使用者的插件生成双向链接。

这三个 Skill 之间共享参考资源，安装时请保留完整的 `skills/` 目录。

## 安装与使用

这是 **Skills 插件源码**，不包含作者的账号连接或 Notion 凭据。公开 GitHub 仓库不会自动将插件发布到 ChatGPT 公共插件目录。

### 在支持仓库插件来源的 Codex / ChatGPT 桌面环境中

使用支持此命令的 Codex CLI 添加来源：

```sh
codex plugin marketplace add automan2006/organize-knowledge
```

然后在支持本地／仓库来源的 ChatGPT 桌面插件界面选择 **Organize knowledge** 来源，安装或启用插件。不同版本的入口和权限可能不同，参见 [OpenAI 官方插件打包与仓库来源说明](https://developers.openai.com/plugins/build/plugins)。安装后开启新对话，让宿主加载新 Skills。

也可下载 [Releases](https://github.com/automan2006/organize-knowledge/releases) 中的插件 ZIP，在支持插件导入的环境中导入；或者让支持 Skills 的代理安装 `plugins/organize-knowledge/skills/` 中的三个 Skill。

### 第一次使用前

1. **连接自己的 Notion**：通过宿主提供的 Notion 连接完成授权。运行时必须实际提供读取、创建和更新页面的工具；图片自动归档还需要可用的图片上传能力。
2. **指定自己的归档位置**：把课程页面或课程数据库链接提供给代理。首次使用不会默认选作者的课程库，也不会任意选择搜索到的页面。
3. **确认时区和保存意图**：明确说“保存到 Notion”后执行归档；只说预览时不写入。
4. **在原学习聊天中调用**：这样更容易取得原始消息和图片。若历史被压缩或附件失效，补充导出的聊天或原图。

可以复制以下提示，替换括号中的内容：

```text
使用 $study-chat-notes 整理当前整条学习聊天。

我的 Notion 课程位置：[粘贴自己的课程页面或数据库链接]
我的时区：[例如 Asia/Shanghai]

保留完整解释、公式推导、例题步骤及追问纠错。
把我发的图片和你输出的配图保存到对应知识点附近。
公式按手机可读宽度选择字号，计算结束后的解释另起一段。
保存到 Notion 后回读检查，再输出可复制的 Obsidian 概念笔记。
请分别报告用户图片和助手配图的成功数量、缺图及原因。
```

只导出 Obsidian 时：

```text
使用 $obsidian-concept-notes 整理当前聊天。
按概念分别输出可复制的 Markdown，附文件名、别名和候选关联。
```

## Notion 笔记布局

![课程笔记布局示意](plugins/organize-knowledge/skills/notion-course-notes/assets/note-layout.svg)

上图是代码绘制的结构示意，不是实际页面截图。桌面布局包括左侧目录、中间正文、右侧重点／公式／图解；例题和易错点安排在下方。手机由 Notion 纵向排列。

重点使用浅色提示框；公式是可编辑的原生数学块。长式不强制大字号，也不把全部计算变成图片。

## 图片与客户端边界

- Skills 只提供工作流，不赋予读取全部聊天、读取手机相册或使用 Notion 的额外权限。
- **看得见图片不等于取得原文件。** 只有当前环境能读取原文件或可访问的图片地址时，才能自动上传。仅有手机截图时可保存截图，但不会把截图里的四个格子算作四张原图已保存。
- Notion 连接可能只提供文字页面工具。若缺少 `create_file_upload` / `create_attachment` 或等效能力，图片自动归档需要更完整的连接，不能靠本插件自行绕过。
- 随包的 JPEG/PNG 上传程序需要 Python 3.9+、原文件和 HTTPS 网络访问；SVG 在提供对应附件工具的环境中可走文本附件路径。
- iPhone、Windows 和网页端取决于账号、宿主插件支持和文件传输能力。本仓库没有对所有端做完整实测。
- 历史被截断、附件过期或图片无法读取时，明确标为“部分完成”并列出待补项。
- 公式宽度工具是保守估算，不会实时读取手机屏幕或在保存后实时缩放字号。

## 随包工具与验证

- `upload_notion_image.py`：使用 Notion 工具返回的上传响应发送真实图片文件；拒绝非预期域名和跳转，不在输出中打印授权头。
- `fit_notion_equation.py`：估算 LaTeX 排版宽度并选择字号，不修改数学内容；超长或未知结构要求拆分／复核。

两个程序只使用 Python 标准库。仓库内的测试不需要真实账号或网络：

```sh
python -m unittest discover -s tests -v
python scripts/validate_public_package.py
```

开发阶段已在 Windows 环境验证 JPEG、SVG 上传与 Notion 图片块回读，并做过 37 个公式的窄宽度浏览器模拟。本公开仓库的独立测试不操作作者的私人页面；真实 iPhone 的 Notion 显示尚未完整实测。

## 数据与开源

公开版不包含作者的 Notion 页面／数据库 ID、账号绑定、个人邮箱、聊天记录、原始截图或上传授权。使用者自行配置自己的账号和位置。处理学习材料时，实际数据流由所选 AI 宿主及 Notion 连接决定；本仓库没有独立托管服务或遥测服务。

问题和建议可提交到 [Issues](https://github.com/automan2006/organize-knowledge/issues)。代码与原创资源使用 [MIT License](LICENSE)，欢迎使用、修改和贡献。
