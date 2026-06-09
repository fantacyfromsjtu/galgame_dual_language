# Dual Subtitle Tool

[English](README.md) | 简体中文

Dual Subtitle Tool 是一个小型工作流仓库，用于给 Kirikiri/KirikiriZ 视觉小说制作游戏内双语文本补丁，尤其适合剧情脚本可以通过 FreeMote 兼容的 M2/KRKR PSB JSON 流程 dump、反编译和重编译的游戏。

它不是“一键通用补丁器”。真正可复用的是这套流程：

1. dump 或抽取已解密的剧情脚本。
2. 用 FreeMote 将脚本反编译成可编辑 JSON。
3. 抽取原文文本行。
4. 从汉化版、本地化版或补丁中收集译文文本行。
5. 对齐原文和译文。
6. 将双语文本写回剧情 JSON。
7. 重编译剧情文件，并打包运行时 XP3 补丁。
8. 用 KrkrPatch 或其他 Kirikiri 补丁加载器加载补丁。

## 包含内容

- 用于 XP3 打包、FreeMote JSON 文本抽取、双语文本写入、内存字符串抽取和对齐的 Python 脚本。
- 用于构建和安装补丁包的 PowerShell 示例。
- KrkrPatch 配置示例。
- 工作流、脚本说明和已知限制文档。

## 不包含内容

- 不包含游戏本体。
- 不包含游戏脚本、图片、字体、音频、截图、存档或生成后的补丁。
- 不包含 FreeMote、KrkrDump、KrkrPatch、KrkrExtract 等第三方二进制工具。
- 不包含任何商业游戏的翻译数据。

你需要自行准备合法取得的游戏文件和第三方工具。

## 仓库结构

```text
scripts/
  xp3_pack.py                    打包简单的未加密 XP3 补丁包。
  xp3_replace_entry.py           原地替换一个未压缩 XP3 条目。
  freemote_batch.py              批量反编译/重编译 FreeMote 剧情文件。
  freemote_extract_texts.py      从 FreeMote 剧情 JSON 抽取文本行。
  freemote_apply_bilingual.py    将译文追加到 FreeMote 剧情 JSON。
  freemote_align_json.py         审计原文/译文 FreeMote JSON，并生成双语 JSON。
  align_memory_strings.py        将内存中的译文字符串对齐到原文行。
  extract_cjk_strings.py         从二进制 dump 中抽取 CJK 字符串。
  scan_process_cjk.py            扫描 Windows 进程中的 CJK 字符串。
  search_process_text.py         在进程内存中搜索精确文本。
  dump_process_region.py         dump 可读进程内存区域。
  parse_krkrdump_log.py          从 KrkrDump 日志抽取 hash/path 映射。

docs/
  WORKFLOW.md                    端到端工作流。
  SCRIPTS.md                     脚本索引和命令示例。
  LIMITATIONS.md                 可移植性和风险说明。
  CAFE_STELLA_CASE_STUDY.md      从原型项目脱敏整理的案例。

examples/
  build_patch.ps1                通用补丁构建/安装辅助脚本。
  krkrpatch/KrkrPatch.example.json
  scenario_map.example.tsv
  json_alignment_overrides.example.tsv
  alignment.example.tsv
```

## 快速开始

目前支持两条对齐路线。

### 推荐路线：直接 JSON 对齐

如果原版和翻译版的剧情脚本都能反编译成结构匹配的 FreeMote JSON，优先使用这条路线：

```powershell
python scripts\freemote_batch.py decompile --input-dir work\orig_scn --output-dir work\orig_json
python scripts\freemote_batch.py decompile --input-dir work\translated_scn --output-dir work\translated_json
python scripts\freemote_align_json.py --map work\scenario_map.tsv --orig-json-dir work\orig_json --translated-json-dir work\translated_json
python scripts\freemote_align_json.py --map work\scenario_map.tsv --orig-json-dir work\orig_json --translated-json-dir work\translated_json --write-bilingual-json --clean
python scripts\freemote_batch.py build --input-dir work\bilingual_json --output-dir work\bilingual_scn
```

将重编译后的 `.ks.scn` 文件，以及每个游戏专属的启动脚本、字体配置等覆盖文件复制到 `work\patch_stage`，然后打包：

```powershell
python scripts\xp3_pack.py work\patch_stage work\dual_sub_patch.xp3
```

### 兜底路线：文本表对齐

如果译文来自内存扫描或其他文本表，而不是译文版剧情 JSON，可以使用这条路线：

```powershell
python scripts\freemote_extract_texts.py work\orig_json -o work\orig_texts.tsv
python scripts\align_memory_strings.py --orig work\orig_texts.tsv --mem-strings work\translated_strings.tsv -o work\aligned.tsv --log-output work\align_log.tsv
python scripts\freemote_apply_bilingual.py --input-json work\orig_json\scene.ks.json --alignment work\aligned.tsv -o work\bilingual_json\scene.ks.json
```

## 文本如何嵌入

本工具不做机器翻译，也不绘制外部悬浮字幕层。它直接编辑剧情 JSON 的文本块：

```text
原文行
```

变成：

```text
原文行
译文行
```

重编译后的剧情文件会作为普通脚本覆盖文件被游戏加载。

完整流程见 [docs/WORKFLOW.md](docs/WORKFLOW.md)，脚本逐项用法见 [docs/SCRIPTS.md](docs/SCRIPTS.md)。

## 当前成熟度

这是从一个成功的全剧情原型中抽取出来的 alpha 质量工具链。它最适合以下情况：

- 游戏基于 Kirikiri/KirikiriZ；
- 剧情脚本可以被 dump 或反编译；
- FreeMote 可以重建该剧情格式；
- 译文文本可以按大致相同顺序收集；
- 运行时补丁加载器可以覆盖单个剧情文件。

不同引擎或高度定制的脚本系统需要额外 adapter。
