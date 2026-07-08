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
| `--cn-first` / `--no-cn-first` | 把**国内片源**（国语/中字/华语/CHN 等）排到前面（**默认开启**，用 `--no-cn-first` 关闭） |
| `--no-remux` / `--remux` | 过滤掉**原盘/Remux**（原盘、Remux、BDMV，体积巨大、播放器兼容性差；**默认开启**，用 `--remux` 保留） |
| `--no-hardsub` | 过滤掉字幕疑似**内嵌/硬字幕**的片源（内嵌、硬字，以及 TC/CAM 枪版带中字的；默认关闭） |
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

# 默认已开启「国内优先 + 排除原盘」，直接搜即可（结果行会标注 国内 / 原盘 / 内封·外挂 / 中字?）
pr-search 流浪地球 2019

# 想看原盘、或关掉国内优先时临时覆盖
pr-search --remux --no-cn-first 流浪地球 2019

# 进一步排除内嵌字幕的版本
pr-search --no-hardsub 流浪地球 2019

# 复制第 1 条结果的磁力到剪贴板（代理结果会自动解析成真磁力）
pr-search --copy 1 ubuntu

# 保存第 2 条结果为 .torrent 文件
pr-search --save 2 ubuntu

# 只输出磁力链接，管道给其他工具
pr-search -m --min-seeders 10 debian

# macOS 下用默认 BT 客户端直接打开第一条结果
pr-search --copy 1 debian && open "$(pbpaste)"
```

## 批量处理（CSV 片单）

给一份包含影片元数据的 CSV，脚本会逐行搜索、按质量排序、解析出标准磁力链接，
并把结果**回填成新的列**（`magnet_1..N`），输出一份新 CSV。

```bash
# 自动识别表头（含 title_en / year 列即可），每部片回填 3 个磁力
pr-search --batch films.csv

# 无表头、列顺序自定义：英文名在第 2 列，年份在第 14 列
pr-search --batch list.csv --no-header --en-col 2 --year-col 14

# 每部片回填 5 个，做种数下限提到 10，指定输出路径
pr-search --batch films.csv --top 5 --min-seeders 10 --out result.csv
```

### 批量选项

| 选项 | 说明 |
|------|------|
| `--batch CSV` | 输入的片单 CSV，逐行处理 |
| `--out CSV` | 输出路径（默认 `<输入名>_magnets.csv`） |
| `--top N` | 每部片回填的磁力数量（默认 3） |
| `--min-seeders N` | 做种数下限（批量模式默认 5） |
| `--cn-first` / `--no-cn-first` | 每部片的候选里国内片源优先回填（默认开启） |
| `--no-remux` / `--remux` | 过滤掉原盘/Remux（默认开启，用 `--remux` 保留） |
| `--no-hardsub` | 过滤掉字幕疑似内嵌/硬字幕的片源（默认关闭） |
| `--min-relevance F` | 标题匹配度阈值 0~1（默认 0.5），低于此值的结果被丢弃 |
| `--no-header` | 输入 CSV 没有表头行 |
| `--en-col` | 英文名列（列名或从 1 开始的序号） |
| `--zh-col` | 中文名列（列名或序号） |
| `--year-col` | 年份列（列名或序号） |

### 列自动识别

有表头时，脚本会自动匹配这些列名（大小写不敏感）：

- 英文名：`title_en` / `english` / `en`
- 中文名：`title` / `title_zh` / `name` / `电影名`
- 年份：`year` / `年份` / `年代`

识别不到时用 `--en-col` / `--zh-col` / `--year-col` 手动指定（可以填列名，也可以填序号）。

### 搜索与排序逻辑

1. **搜索关键词**：优先用「英文名 + 年份」（公共站命中率最高）。搜不到时依次回退到
   「仅英文名」→「中文名 + 年份」。
2. **相关性过滤**：Prowlarr 结果没有题材字段，脚本用**标题连续匹配**判断相关性——
   要求片名的词在结果标题里按顺序连续出现。这样 `21 Grams` 能匹配
   `21.Grams.2003.1080p`，但不会误匹配动漫第 21 集 `... - 21`。年份匹配加分，
   剧集标记（`S01E02`、`- 21`、`[12]`）扣分。
3. **质量排序**：从标题解析分辨率、片源、编码，加权综合做种数打分：
   - 分辨率：2160p/4K > 1080p > 720p > 480p（权重最高）
   - 片源：Remux > BluRay > WEB-DL > HDTV > DVD > CAM
   - 编码：AV1 > x265/HEVC > x264
   - 做种数：折算加分（有封顶，避免高做种的低画质顶掉 1080p）
   - 疑似假种（文件 <200MB）扣分
   - 最终排名 = 质量分 × 相关性，相关性作为乘数压制噪音
4. **回填**：每部片取前 `--top` 名，每个结果写入 4 列：
   `magnet_N`（标准磁力）、`quality_N`（如 `1080p/BluRay/x265`，另会带
   `国内` / `原盘` / `内封` / `中字` 等标签）、`seeders_N`（做种数）、
   `title_N`（原始发布标题）。默认已开启「国内优先 + 排除原盘」，可用
   `--no-cn-first` / `--remux` 覆盖，`--no-hardsub` 进一步排除内嵌字幕。

> 注意：因为逐行都要请求 Prowlarr（还要解析 .torrent），批量处理**较慢**，
> 每部片约几秒。片单大时建议先小批量试跑。

## 工作原理说明

不同索引器返回的下载信息不一样：

- **公共磁力站**（如 Nyaa.si）：搜索结果里直接带 `magnet:` 链接，瞬间返回。
- **代理型站点**（如 1337x）：搜索结果只给一个 Prowlarr 代理 URL，访问它会返回真正的 `.torrent` 文件。此时脚本会在你使用 `--copy` / `-m` / `--save` 时按需下载该文件并解析成标准磁力链接。

表格显示时，`magnet` 绿色标签表示可直接拿到磁力，`proxy` 黄色标签表示需要解析（在复制/保存时自动完成）。因为逐行解析会产生网络请求，所以列表阶段不会预先解析，只在你真正需要某一条时才处理。

### 关于做种数（seeders）

部分索引器是**磁力/DHT 聚合站**（如 52BT、BTdirectory、Magnet Cat），它们本身不跟踪 swarm，会给每条结果填一个固定占位值（通常 `seeders=1`），并不是真实做种数。脚本会自动识别这种情况——当某索引器在同一次搜索里返回的做种数**完全不变且 ≤1** 时，判定其做种数不可信，于是：

- 表格里显示成 `S:?` 而不是骗人的 `S:1`；批量 CSV 的 `seeders_N` 列写成 `?`；
- **不会**被 `--min-seeders` 过滤掉（无从判断，就不误杀）；
- 按 `seeders` 排序时排在有真实做种数据的结果之后；
- 质量打分里做种数分取中性值，既不加分也不因「1 种」被压低。

真正的 tracker 站（Nyaa.si、BigFANGroup 等）返回的做种数是真实的，照常参与过滤和排序。
