# dsh-market-index

DSH（DeepSeek Harness）插件市场索引，format 1。供桌面版 **设置 → 插件 → 发现** 读取。

索引地址：

```
https://cdn.jsdelivr.net/gh/peihao0928/dsh-market-index@main/index.json
```

## 内容

面向**系统集成与运维**的 DSH 插件，24 条，来源为 [1024Store](https://deepseek1024.com) 社区目录，逐条用 npm registry 元数据核对：

- 包必须在 npm 上存在，且 `package.json` 里有 `dsh.bundle`（否则市场装了也不会加载）；
- 版本取 npm 的 `latest`，`publishTimestamp` 取该版本发布时间；
- 分类：`ssh` / `monitor` / `backup` / `container` / `database` / `network` / `deploy` / `tools`。

## 重新生成

```bash
python3 build_index.py index.json
```

脚本会：搜 1024Store → 解析 `install` 命令拿包名 → 并发查 npm 确认是 bundle → 生成索引。
生成后用官方校验器验一遍：

```js
import { parseMarketIndex } from '@deepseek-ai/dsh-plugin-market-index'
parseMarketIndex(JSON.parse(fs.readFileSync('index.json')), indexUrl)
```

## 注意

- 索引不做安全背书。安装第三方插件等于让对方代码在你的 host 进程里运行，装之前看 README 和源码。
- 1024Store 的搜索接口有速率限制（429），批量跑脚本时加 `sleep`。
- 本仓库只是索引的托管处；`format: 1` 的字段语义由 DSH 的 `dsh-plugin-market-index` 定义。
