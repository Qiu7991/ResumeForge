// SPDX-License-Identifier: Apache-2.0
/**
 * 采集页签里的采集条件表单、采集账目提示与历史条件下拉标签。
 *
 * 覆盖 `features/apply/collect/` 下的 `CollectConfigForm`、`CollectOutcomeAlerts`
 * 与 `collectConfigHistory`；「按招聘网站的条件筛」那一块仍由 `collectFilters` 包负责。
 */
const applyCollect = {
  "applyCollect.field.source": "采集来源",
  "applyCollect.source.search": "关键词搜索",
  "applyCollect.source.interest": "我的感兴趣",
  "applyCollect.hint.interest":
    "BOSS「感兴趣」是你的个人岗位列表，不需要关键词和城市条件；岗位会连同完整 JD 存进暂存区。",
  "applyCollect.field.interestScanLimit": "只看最新 N 个收藏",
  "applyCollect.hint.interestScanLimit":
    "从最新收藏往下数这 N 个（跳过的那几个也占位置）；0 = 看全部。避免为了几条新岗位翻完几百个旧收藏。",
  "applyCollect.field.interestMaxPages": "感兴趣翻页上限（页）",
  "applyCollect.hint.interestMaxPages": "每页固定 15 条；10 页约 150 条。",
  "applyCollect.field.keywords": "关键词",
  "applyCollect.hint.keywords": "最多 10 个；与城市至少要填一个。",
  "applyCollect.placeholder.keywords": "例如：市场营销、财务会计",
  "applyCollect.field.city": "城市",
  "applyCollect.placeholder.city": "例如：北京",
  "applyCollect.field.perTaskLimit": "单批上限",
  "applyCollect.field.intervalSeconds": "岗位间隔（秒）",
  "applyCollect.field.jitterSeconds": "随机抖动（秒）",
  "applyCollect.field.saveSamples": "保存本次抓到的站点原文（用于排查解析问题）",
  "applyCollect.hint.saveSamples":
    "会保存搜索与详情两个接口的响应原文；只存到本机 backend/data/captures/，不进仓库、不进备份。",
  "applyCollect.action.save": "保存条件",
  "applyCollect.action.start": "开始采集",
  "applyCollect.history.keywordSeparator": "、",
  "applyCollect.history.noKeywords": "无关键词",
  "applyCollect.history.noCity": "无城市",
  "applyCollect.outcome.listSeparator": "、",
  "applyCollect.outcome.interest.invalid": "已跳过 {count} 条失效岗位",
  "applyCollect.outcome.interest.scan":
    "本轮查看了 {scanned} 个收藏岗位，其中 {known} 个之前已经采集过（不再重复入库）",
  "applyCollect.outcome.interest.scanHint":
    "「之前采集过」指更早的采集批次已经把它们放进暂存区了——去「采集记录」里勾选导入即可，不用重采。想少看一些就把「只看前 N 个收藏」调小。",
  "applyCollect.outcome.pagination.title":
    "后面的页与前面的结果完全重复，已在第 {page} 页提前停止翻页",
  "applyCollect.outcome.pagination.description":
    "该条件下的岗位可能就这么多，或者大多已经采集过。想采更多：换关键词 / 城市，或放宽筛选条件后再跑一次。",
  "applyCollect.outcome.unmapped.title": "以下条件未生效",
  "applyCollect.outcome.unmapped.description":
    "这批采集里，{conditions} 无法映射到该站点的查询参数，因此没有按它们筛选；结果里可能包含不满足这些条件的岗位。关键词、城市与翻页正常生效。",
  "applyCollect.outcome.siteFiltered.appliedTitle":
    "招聘网站已按这些条件筛掉不符合的岗位：{conditions}",
  "applyCollect.outcome.siteFiltered.unappliedTitle": "有筛选条件没能生效",
  "applyCollect.outcome.siteFiltered.unappliedDescription":
    "这些条件本次没有生效：{conditions}——编码没能在站点当前的清单里核对上，所以没有发出去（发一个对不上的编码， 网站会照常返回结果，你会以为筛过了）。点上面「重新读取」刷新清单后再试。",
  "applyCollect.outcome.siteFiltered.appliedDescription":
    "网站在搜索时就完成了这些筛选，所以结果里不会有不符合的岗位。",
} as const;

export default applyCollect;
