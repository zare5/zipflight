<p align="center">
  <img src="docs/assets/banner.svg" alt="Zipflight — 在发出 ZIP 前，检查文件名兼容性" width="100%">
</p>

<p align="center"><a href="README.md">English</a> · <a href="#快速使用">快速使用</a> · <a href="#检查什么">检查项目</a> · <a href="docs/alternatives.md">同类工具</a></p>

# Zipflight — 发出 ZIP 前，先检查一下

**提前找出 ZIP 中可能无法解压、互相覆盖，或换个系统就改变含义的文件名。**

ZIP 格式有效，不代表里面的文件名适合每个平台。例如 `CON.txt`、同时存在的 `Readme.md` 和 `README.md`，或者一个名为 `assets` 的文件加上 `assets/logo.png`。Zipflight 读取压缩包的元数据，在你发布版本或发送文件前解释这些问题。

```sh
zipflight release.zip
```

- **把冲突双方放在一起展示**，附上原因和处理建议。
- **指定目标平台**：Windows、macOS、Linux，或默认的保守跨平台检查。扫描结果不依赖当前运行系统。
- **输出终端文本、Markdown 或 JSON**，方便查看、贴入 issue 或接入 CI。
- **完全本地运行**：不上传、无账户、无遥测、无运行时第三方依赖。不解压、不重命名，也不处理条目的文件内容。

## 适合什么时候用？

| 场景 | 可以检查的内容 |
| --- | --- |
| 在 Linux 上打包，发布给 Windows 用户。 | 保留设备名、非法字符、大小写冲突和路径长度。 |
| Mac 上正常的 ZIP，到客户的 Windows 上打不开。 | 平台相关文件名、旧编码标记和解压要求。 |
| 解压后文件少了，或互相覆盖。 | 重复条目、等价名称、文件与目录冲突。 |
| 希望发布前发现这些问题。 | 本地运行，或把检查加入 CI。 |

Zipflight 是一个**跨平台兼容性预检工具**。它不修复文件名、不验证文件内容或 CRC、不查杀恶意软件，也不保证压缩包可以安全解压。通过检查只表示已实现的元数据规则没有发现问题，不代表所有解压软件都能正确处理。

## 快速使用

需要 **Python 3.10+**。下面的安装方式还需要 Git：

```sh
python -m pip install "git+https://github.com/zare5/zipflight.git@v0.1.0"
zipflight --demo
zipflight "path/to/archive.zip"
```

演示创建一个临时压缩包，故意放入有问题的文件名，扫描后自动清理，退出码为 **1**。不会解压这些条目。

`zipflight --demo` 的实际输出节选（省略了其他检查结果）：

```text
Zipflight 0.1.0 | demo.zip
FAIL | 7 entries | target: portable

ERROR [windows-reserved-name] A path component is a reserved Windows device name.
  "notes/CON.txt"
  Fix: Rename the component, including names such as CON.txt or COM1.

ERROR [file-directory-conflict] This path must be both a file and a directory (possibly an implicit parent).
  "docs"
  "docs/guide.txt"
  Fix: Rename the file or the directory tree so both can exist.
```

**没有 Git：** 从 [Releases](https://github.com/zare5/zipflight/releases/latest) 下载 `zipflight-0.1.0-py3-none-any.whl`，然后运行：

```sh
python -m pip install zipflight-0.1.0-py3-none-any.whl
```

**不想安装 Python 包：** 从同一个发布页面下载 `zipflight.pyz`：

```sh
python zipflight.pyz --demo
python zipflight.pyz archive.zip
```

**Windows 上没有 Python：** 下载 `zipflight-windows-x64.exe`，在 PowerShell 中运行：

```powershell
.\zipflight-windows-x64.exe --demo
.\zipflight-windows-x64.exe .\archive.zip
```

Windows 可执行文件是未签名的命令行程序，需要在终端里运行。目前尚未发布到 PyPI，请使用上述安装方式。

## 检查什么？

以下只是压缩包条目示例，不会在你的电脑上创建这些文件。

| 检查 | 示例 | 可能的问题 |
| --- | --- | --- |
| Windows 文件名 | `CON.txt`、`notes:final.txt`、`report. ` | 保留设备名、非法字符、结尾的点或空格。 |
| 大小写与 Unicode 冲突 | `Readme.md` 与 `README.md`；`café.txt` 的两种 Unicode 写法 | 不同条目可能落到同一个目标文件。 |
| 重复条目 | 两个都叫 `data.csv` 的条目 | 不同解压程序可能保留不同副本。 |
| 文件与目录冲突 | `assets` 与 `assets/logo.png` | 同一个位置不能同时是文件和父目录。 |
| 路径结构 | `../outside.txt`、绝对路径、反斜杠 | 路径可能被拒绝或被不同方式解释。 |
| 长度限制 | 深层目录加上较长的解压目标路径 | 部分 Windows 工具仍受旧版 260 单位路径限制。 |
| 解压要求 | 加密、符号链接、特殊压缩方法 | 解压软件的支持程度和行为不同。 |
| 其他元数据 | 旧编码的非 ASCII 文件名、系统杂项、极高的声明膨胀比例 | 提供排查和分享前的参考信息。 |

还会提示控制字符和双向文本格式字符，它们可能让文件名的显示具有误导性。

完整的问题代码、严重程度和适用平台，见[检查规则参考](docs/checks.md)。

### 选择接收方平台

```sh
zipflight archive.zip --target windows
zipflight archive.zip --target macos
zipflight archive.zip --target linux
```

默认的 `--target portable` 综合使用较保守的平台规则。这些规则不是对 NTFS、APFS、ext4 或具体解压程序的完整模拟。Unicode 和大小写碰撞采用保守的 NFC/casefold 近似判断，实际文件系统规则可能不同。

### 为解压目录预留长度

Windows 旧版路径检查默认给解压目标目录预留 **40 个 UTF-16 代码单元**。如果接收方通常会解压到较深的目录，可以增加估计值：

```sh
zipflight release.zip --target windows --root-length 80
```

`--root-length` 表示不含末尾分隔符的目标目录长度。Zipflight 会另加一个分隔符，再加压缩包内的条目路径长度。它不检查真实文件系统，也不知道最终解压位置；支持长路径的工具可能不受旧限制影响。

## 报告和自动化

通过终端重定向保存报告：

```sh
zipflight archive.zip --format markdown > zip-report.md
zipflight archive.zip --format json > zip-report.json
```

JSON 包含 `schema_version`、汇总计数，以及每条结果的稳定代码、严重程度、相关路径、解释和建议。字段说明和错误响应见[报告格式参考](docs/report-format.md)。报告会包含文件名，分享前请检查。

默认情况下，警告会显示，但不会让命令失败。发布检查可以使用更严格的 `--fail-on warning`：

```sh
python -m zipflight release.zip --target portable --fail-on warning
```

| 退出码 | 含义 |
| --- | --- |
| `0` | 没有达到所选失败阈值的问题。 |
| `1` | 发现错误，或在 `--fail-on warning` 下发现警告。 |
| `2` | 无法完成扫描，或命令参数无效。 |

GitHub Actions 中，在**构建出 ZIP 之后**加入：

```yaml
- uses: actions/setup-python@v7.1.0
  with:
    python-version: '3.12'
- run: python -m pip install "git+https://github.com/zare5/zipflight.git@v0.1.0"
- run: python -m zipflight dist/release.zip --target portable --fail-on warning
```

## 范围和同类工具

Zipflight 读取中央目录及相关压缩包元数据，不验证压缩内容、本地文件头一致性、校验和、磁盘空间、权限或嵌套压缩包。大小和膨胀比例来自压缩包自行声明的数值，不是真实内容测量。超出元数据限制的大型压缩包可能被拒绝扫描，不会被当作部分通过。条目数量、元数据大小、路径深度和报告条数的具体限制，见[边界与不支持的结构](docs/report-format.md#bounds-and-unsupported-structures)。

验证文件内容完整性，可使用 `unzip -t` 或压缩软件。处理不可信压缩包，应选择针对安全解压设计的工具。文件名修复、编码转换和源码目录检查，可参考[同类工具对比](docs/alternatives.md)。

[调研记录](docs/research.md)列出了相关问题和选择这个小范围功能的原因。它们是需求线索，不是“市场上没人做过”的证明。

## 开发

```sh
git clone https://github.com/zare5/zipflight.git
cd zipflight
python -m unittest discover -s tests -v
python -m zipflight --demo
```

发现误报或漏报，可以提交目标平台、问题代码和最小文件名列表。不需要上传私人压缩包。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

使用 MIT 许可证，见 [LICENSE](LICENSE)。
