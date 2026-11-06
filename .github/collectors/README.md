# 领聚新闻自动任务

**当前已按用户确认的转载授权升级为全文及原图自动发布。当前工作流、权限、去重和恢复方式见[已授权发布说明](AUTHORIZED-PUBLISHING.md)。以下保留的是旧版元信息采集模式说明，不代表当前线上发布行为。**

目标栏目：https://www.ljglobal.cn/category/news/

栏目HTML公开声明的RSS地址：https://www.ljglobal.cn/category/news/feed/ 。使用该订阅获取标题、日期、网址与最多350字符的短摘要，不请求文章详情或下载原图，不改写竞品文章，不直接发布到chaudizhi.com。

## 自动运行

工作流：`.github/workflows/collect-ljglobal.yml`。

- 每天北京时间11:17（UTC03:17）调度检查，距上次**成功采集**达到72小时才请求来源。不是`*/3`日号规则，因此跨月仍按72小时门槛判断。
- 首次提交自动运行，也可在Actions中手动运行。手动勾选force可立即采集，仍按网址去重。
- GitHub调度可能延迟或被跳过；如果最后成功运行不在每日检查时刻，实际采集间隔可能超过72小时，通常为72至96小时。不是实时定时服务。
- 采集失败不推进游标，次日调度会再次尝试。HTTP403、重定向、robots无法核实或禁止时直接失败，不做绕过。
- 同一工作流不并发采集，避免两个任务覆盖状态。
- 公共仓库长期无活动时，GitHub可能自动停用定时工作流；在Actions页面检查状态，不通过空提交伪造活跃。

## 结果与去重

Actions运行成功且实际采集时，下载`ljglobal-topics-运行号`产物：

- `topics.json`：本次订阅条目与新增条目，后台核查用。
- `topics.rss`：只含新增选题的简化RSS，可导入本地内容工作台。
- `report.json`：采集时间、条目数与范围说明。

这些产物保留90天，受GitHub仓库及Actions访问权限约束，**不是保密存储**。不放客户信息、凭据或身份资料。来源链接保留用于核查，但不会插入网站公开文章。

`collector-state`分支仅用于保存`.collector/ljglobal-state.json`，内容为最后成功时间与网址哈希，不包含文章正文或原链接。它不触发现有仅针对main的Pages部署。

先上传产物，成功后才推进去重状态。若状态保存失败，本次产物仍可下载；下一次可能重新收集同一批选题，但不会将采集结果冒充已发布文章。不要删除状态分支来“清理报错”，否则会重置历史去重。

当前RSS通常仅提供10条近期内容，并不保证覆盖全部历史文章；如果三天内源站更新超过订阅窗口，可能漏掉窗口外条目。本版不承诺全站历史采集。需更完整覆盖时，应取得站方允许的完整Feed或归档接口，而不是擅自抓全文。

## 网站发布边界

按当前选择，不接AI接口，也不自动搬运文章。下一步在本地工作台导入topics.rss，人工写/导入自有原创稿，审核后再生成网站文件。自动任务不会改动index.html、pages/或sitemap.xml。

前台不显示参考来源，不等于可以去除第三方作品的必要署名。此任务仅用于选题元信息，不把竞品全文翻译或洗稿后作为本站原创发布。robots允许抓取不代表给予转载版权。

## 权限和验证

不需要额外API密钥。工作流仅使用运行时GITHUB_TOKEN，采集作业需要contents:write以维护状态分支；代码固定只写该分支。网站部署权限未增加，checkout不持久化Git凭据，不强制推送。

Python仅用标准库，Ubuntu runner自带python3即可，无pip依赖。第三方Actions固定到已核对的提交SHA。不要改成pull_request_target执行不可信分支代码。

本地测试：

```text
python -m unittest discover -s .github/collectors -p "test_*.py" -v
python .github/collectors/ljglobal.py --local-state /absolute/private/state.json --out /absolute/private/output --force
```

使用默认命令而未提供local-state时，会读取GITHUB_REPOSITORY对应的状态分支；本地通常使用显式local-state。真正的Actions运行成功、产物存在且状态分支更新后，才可称为GitHub端已验证。
