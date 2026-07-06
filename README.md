# pr-search

通过本地 [Prowlarr](https://github.com/Prowlarr/Prowlarr) 实例在命令行搜索种子 / 磁力链接的小工具。纯 Python 3 标准库实现，无需 `pip install`。

## 特性

- 一条命令搜索所有已配置的索引器，默认按做种数排序
- 自动从 Prowlarr 的 `config.xml` 读取 API key（也可用环境变量覆盖）
- 按分类、索引器、最小做种数过滤
- **自动解析真实磁力链接**：对于 1337x 等只返回代理下载链接的站点，自动下载 `.torrent` 文件、解析出 infohash 与 tracker，拼成标准 `magnet:` 链接（内置纯标准库的 bencode 解析器）
- 一键复制磁力到剪贴板，或直接把 `.torrent` 文件保存到本地
- 管道友好的纯磁力输出 / 原始 JSON 输出

## 依赖

- Python 3（macOS 自带）
- 一个运行中的 Prowlarr 实例（默认 `http://localhost:9696`）
- `--copy` 功能依赖 macOS 的 `pbcopy`

## 安装

脚本已带可执行权限，可直接用：

```bash
~/Documents/pr-search/pr-search ubuntu
```

想全局调用，可软链到 PATH：

```bash
ln -s ~/Documents/pr-search/pr-search /usr/local/bin/pr-search
```

之后即可直接 `pr-search ubuntu`。

## 配置

默认无需配置——脚本会自动从以下位置读取 API key：

```
~/Library/Application Support/Prowlarr/config.xml
```

可用环境变量覆盖：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PROWLARR_URL` | `http://localhost:9696` | Prowlarr 地址 |
| `PROWLARR_KEY` | 从 config.xml 读取 | API key |

## 用法

```
pr-search [选项] 搜索词...
```

### 选项

| 选项 | 说明 |
|------|------|
| `-n, --limit N` | 最多显示 N 条结果（默认 25） |
| `-i, --indexers a,b` | 只搜索指定索引器 id（逗号分隔） |
| `-c, --categories a,b` | 只搜指定分类 id（如 `2000`=电影，`5000`=电视） |
| `-s, --sort KEY` | 排序方式：`seeders`（默认）/ `size` / `age` |
| `--min-seeders N` | 过滤掉做种数低于 N 的结果 |
| `-m, --magnets` | 只输出磁力链接，每行一条（适合管道） |
| `--copy N` | 复制第 N 条结果的磁力到剪贴板 |
| `--save N` | 把第 N 条结果的 `.torrent` 文件下载到当前目录 |
| `--json` | 输出原始 JSON |
| `--list-indexers` | 列出所有索引器及其 id，然后退出 |

### 常用分类 id

| id | 分类 |
|----|------|
| 2000 | 电影 |
| 5000 | 电视 |
| 3000 | 音频 |
| 7000 | 书籍 |
| 8000 | 其他 |

（完整分类可参考搜索结果里的 `categories` 字段，或各索引器的 capabilities。）

## 示例

```bash
# 列出已配置的索引器
pr-search --list-indexers

# 基本搜索，按做种数排序
pr-search ubuntu 24.04

# 只看做种数 >= 5 的电影，限定索引器 1、5、4
pr-search --min-seeders 5 -c 2000 -i 1,5,4 There Is No Evil

# 复制第 1 条结果的磁力到剪贴板（代理结果会自动解析成真磁力）
pr-search --copy 1 ubuntu

# 保存第 2 条结果为 .torrent 文件
pr-search --save 2 ubuntu

# 只输出磁力链接，管道给其他工具
pr-search -m --min-seeders 10 debian

# macOS 下用默认 BT 客户端直接打开第一条结果
pr-search --copy 1 debian && open "$(pbpaste)"
```

## 工作原理说明

不同索引器返回的下载信息不一样：

- **公共磁力站**（如 Nyaa.si）：搜索结果里直接带 `magnet:` 链接，瞬间返回。
- **代理型站点**（如 1337x）：搜索结果只给一个 Prowlarr 代理 URL，访问它会返回真正的 `.torrent` 文件。此时脚本会在你使用 `--copy` / `-m` / `--save` 时按需下载该文件并解析成标准磁力链接。

表格显示时，`magnet` 绿色标签表示可直接拿到磁力，`proxy` 黄色标签表示需要解析（在复制/保存时自动完成）。因为逐行解析会产生网络请求，所以列表阶段不会预先解析，只在你真正需要某一条时才处理。
