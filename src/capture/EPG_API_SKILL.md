# IPTV 智慧大屏 EPG 接口 Skill 参考

> 来源：D:\工作\知识库code\Library\02-Areas\EPG接口文档 (8个接口)
> 作者：罗发明、夏凌杰、曾红财

---

## 一、模块归属总览

| 接口编号 | 接口名称 | EPG 接口路径 | 所属模块 |
|---------|---------|-------------|---------|
| 1.1 | 业务主入口 | /IPTV_EPG/StartUp/EPGIndex | StartUp 启动模块 |
| 1.2 | 获取业务能力版本号 | /IPTV_EPG/StartUp/GetAbilityVersion | StartUp 启动模块 |
| 1.3 | 时钟同步接口 | /IPTV_EPG/StartUp/SyncTime | StartUp 启动模块 |
| 4.1 | 获取终端UI数据 | /IPTV_EPG/TerminalUI/GetInitMetaData | TerminalUI 终端UI模块 |
| 4.2 | 获取公共图片 | /IPTV_EPG/TerminalUI/GetPublicImage | TerminalUI 终端UI模块 |
| 4.3 | 子频道专题接口 | /IPTV_EPG/TerminalUI/GetSubChannelData | TerminalUI 终端UI模块 |
| 4.5 | 获取频道首页导航接口 | /IPTV_EPG/TerminalUI/channelList | TerminalUI 终端UI模块 |
| 4.6 | 获取首层导航列表接口 | /IPTV_EPG/TerminalUI/guidePlusList | TerminalUI 终端UI模块 |

---

## 二、公共请求参数

所有接口均 HTTP GET + 固密组加解密。

### 基础参数（所有接口必含）

| 参数名 | 说明 | 类型 | 必选 |
|-------|------|------|-----|
| version | 终端版本号 | String | 是 |
| userId | 用户盒端账号 | String | 是 |
| userMac | 用户盒端 MAC | String | 是 |
| userIp | 用户盒端 IP | String | 是 |
| pf | 平台标识 (0:IPTV / 1:OTT) | String | 否(联通环境需要) |

### TerminalUI 模块额外参数

| 参数名 | 说明 | 适用接口 |
|-------|------|---------|
| areaCode | 地区码 | 4.1/4.5/4.6 |
| templateId | 模板ID | 4.1 |
| instanceId | 实例ID，空=首层导航；非空=二级导航 | 4.1/4.5 |
| isGarden | 后花园标识(固定值:garden) | 4.1 |
| imageGroup | 图片分组(product/background/all) | 4.2 |
| specialId | 专题ID | 4.3 |
| purposeTaskId | 用户分层 | 4.5/4.6 |
| support | 终端能力位(每位代表一种能力) | 4.1/4.5/4.6 |
| groupId | 政企封套分组ID | 4.5/4.6 |
| abt | ABTest 参数 | 4.1/4.6 |
| verMod | 模式(0标准/1少儿/2老年/9教育) | 4.6 |
| style | 样式(1标准/2沉浸式) | 4.6 |
| specialMod | 专用模式(兼容verMod) | 4.6 |

---

## 三、各接口详细说明

### 3.1 业务主入口 (1.1 EPGIndex)

**路径:** /IPTV_EPG/StartUp/EPGIndex

**功能:** 终端启动入口，返回所有子模块 URL 基地址 + 终端下行参数，是 IPTV 会话配置总源。

**返回结构:**
```
epgUrl/
  ├── startUpUrl       → /IPTV_EPG/StartUp
  ├── mediaAssetsUrl   → /IPTV_EPG/MediaAssets
  ├── searchEngineUrl  → /SearchEngine
  ├── channelUrl       → /IPTV_EPG/Channel
  ├── terminalUIUrl    → /IPTV_EPG/TerminalUI
  ├── userDataUrl      → /IPTV_EPG/UserData
  └── AAAUrl           → /AAA
domianConfig[]/         → 域名兜底重试配置
  ├── baseUrl          → 基础URL路径
  ├── retryCount       → 重试次数
  └── retryDomain[]    → 兜底域名列表
parameterList[]/        → 终端下行参数集
  ├── parameterKey     → 参数键
  └── parameterValue   → 参数值(JSON对象或字符串)
result/
  ├── state            → 成功返回0
  └── reason           → 原因
```

**关键下行参数:** advertising_parameters(广告参数含ad_url/timeout/角标ID等)、after_day_playbill_by_current(回看天数)、before_day_playbill_by_current

---

### 3.2 获取业务能力版本号 (1.2 GetAbilityVersion)

**路径:** /IPTV_EPG/StartUp/GetAbilityVersion

**功能:** 返回终端支持的业务能力版本号，用于差异化能力适配。

**额外请求参数:**
| 参数名 | 说明 | 类型 | 必选 |
|-------|------|------|-----|
| otherCp | 第三方业务CPID | String | 否 |
| otherAbility | 第三方业务能力标识(多个用|分隔) | String | 否 |
| areaCode | 地区码 | String | 否 |

**返回字段:**
| 字段 | 说明 | 类型 |
|-----|------|------|
| abilityVersion | 能力版本号(如YYS.5.1.0.Y28.0.HNLT...) | String |
| areaCode | 地区码 | String |
| ip | 终端IP | String |
| bussId | 业务号 | String |
| cp | CP代码 | String |
| support | 能力标识 | String |
| fileformatdesc | 多清晰度标识(0,1,2,3,4) | String |
| verMod | 用户模式 | String |
| parameterList[] | 终端下行参数集 | String |
| result/state | 成功返回0 | String |
| result/reason | 原因 | String |

---

### 3.3 时钟同步接口 (1.3 SyncTime)

**路径:** /IPTV_EPG/StartUp/SyncTime

**功能:** 机顶盒时钟同步，最轻量接口。

**返回:** { "time": "20190402184839" } (格式: yyyyMMddHHmmss)

---

### 3.4 获取终端UI数据 (4.1 GetInitMetaData) ⭐核心

**路径:** /IPTV_EPG/TerminalUI/GetInitMetaData

**功能:** 终端UI初始化元数据，包含模板实例和推荐位集合数据，是 EPG UI 渲染的核心数据源。

**完整返回结构:**
```
templateDatas[]/
  ├── templateId              → 模板ID
  ├── templateName            → 模板名称
  ├── instacneId              → 实例ID
  ├── instacneName            → 实例名称
  ├── isAddZhengqi            → 是否添加正奇
  ├── isIndustry              → 是否行业
  ├── orderNum                → 排序号
  ├── purposeTaskAllow        → 允许任务
  ├── purposeTaskForbid       → 禁止任务
  ├── thumbnail1              → 缩略图1
  ├── thumbnail2              → 缩略图2
  ├── zhengqiAnchors          → 正奇主播
  ├── abTest                  → AB测试
  ├── bgImg                   → 背景图
  ├── bindUserstyle           → 用户样式绑定
  ├── businessAllow           → 允许业务
  ├── businessForbid          → 禁止业务
  ├── channelMode             → 频道模式(int: 1通用分频/2沉浸式/3选片大师/4播放记录)
  └── datas[]/                 → 实例下推荐位集合
        ├── dataId            → 推荐位数据ID
        ├── serialNumber      → 推荐位序号(从1开始)
        ├── title             → 推荐位标题
        ├── watchingFocus     → 精彩看点
        ├── detailedInfo      → 详细信息
        ├── defaultImage      → 默认海报(URL)
        ├── focusImage        → 焦点海报(URL)
        ├── selectedImage     → 选择海报(URL)
        ├── cornerMarkImage   → 角标图(URL)
        ├── cornerMarkPosition→ 角标位置(1左上/2右上/3左下/4右下)
        ├── updateMark        → 更新角标
        ├── clipAttraction    → 合集看点标签(逗号分隔)
        ├── cpId              → 供片方ID
        ├── pluginsSupport    → 插件支持
        ├── filterRuleJson    → 过滤规则JSON
        ├── _menta_data       → 元数据相关
        │   ├── module_menta_data → 模块元数据(platform_mid/external_id/cms_mid/platform_channelid)
        │   └── offset_menta_data → 推荐位偏移元数据(pool_id/pool_cata/pool_type/source_id/source_title/material_id/offset_id/source_type/offset_seq/jumpdata/videoId/originalId/index)
        ├── extendProperties[]/ → 扩展属性
        │   ├── exKey         → 扩展KEY
        │   ├── exType        → 扩展类型(string/image)
        │   └── exValue       → 扩展值
        ├── defaultActions/   → 默认行为动作(28个字段)
        ├── focusActions/     → 焦点行为动作(28个字段)
        ├── selectedActions/  → 选中行为动作(28个字段)
        ├── loadingActions/   → 加载行为动作(28个字段)
        ├── defaultTemlpateData/ → 绑定模板默认数据
        │   ├── (同datas[]结构, 含自身datas[]/defaultActions/focusActions/...)
        │   ├── templateId    → 模板ID
        │   ├── templateName  → 模板名称
        │   └── instacneId/instacneName/...
        ├── focusTemlpateData/  → 焦点模板数据
        ├── selectedTemlpateData/ → 选中模板数据
        └── loadingTemlpateData/ → 加载模板数据
result/
  ├── state                   → 成功返回0
  └── reason                  → 原因
```

**行为动作对象(28字段):**
```
defaultActions/focusActions/selectedActions/loadingActions:
  action              → 行为动作标识(如m_open_player)
  webUrl              → WEB URL
  appPackage          → APP包名
  appName             → APP名称
  exInfo              → 扩展信息(如ChannelNumber=1)
  className           → 类名
  version             → 版本号
  downloadUrl         → 下载URL
  md5                 → MD5
  appCode             → APP代码
  videoId             → 视频ID
  videoType           → 视频类型(0点播/1直播/2节目单)
  point               → 评分
  allIndex            → 总集数
  newIndex            → 新集数
  originalId          → 原始ID
  rootCategoryId      → 根分类ID
  categoryId          → 分类ID
  videoIndex          → 视频索引
  programId           → 节目ID
  beginTime           → 开始时间
  timeLen             → 时长
  specialId           → 专题ID
  starId              → 明星ID
  bindTemplateId      → 绑定模板ID
  bindTemplateName    → 绑定模板名称
  bindInstanceId      → 绑定实例ID
  bindInstanceName    → 绑定实例名称
  (以及 isOuter, isTurnPlay, fullScreen, hotPointId, hotPointId_4k, hotPointId_hd, instTips, kindList, mode, modeUiType, ocid, ovid, poolId, selectKindList, senseType, subBindInstanceId, subtopicId, subtopicIdList, tagId, tagName, topId, topicId, turnplayTimeSwitch, verMod, artistId, busId, cid, cpId, datestyle, definition, feedRecommendSwitch, ... 共63个字段)
```

---

### 3.5 获取公共图片 (4.2 GetPublicImage)

**路径:** /IPTV_EPG/TerminalUI/GetPublicImage

**功能:** 获取产品包图片和背景图片(皮肤包)。

**返回结构:**
```
productImageGroup[]/  → 产品包图片
  ├── id              → 图片ID
  ├── name            → 图片名称
  ├── imageCode       → 图片标识code
  ├── imageUrl        → 图片地址
  ├── extendImageUrl  → 扩展图片地址
  ├── detailedInfo    → 详细信息
  └── extendInfo      → 扩展信息
backgroundGroup[]/    → 背景图片(皮肤包)
  (结构同productImageGroup)
result/
  ├── state           → 0
  └── reason          → OK
```

---

### 3.6 子频道专题接口 (4.3 GetSubChannelData)

**路径:** /IPTV_EPG/TerminalUI/GetSubChannelData

**功能:** 根据专题ID获取专题页数据，支持4种类型(列表/WEB/LIVESHOW/模板)。

**返回字段:**
| 字段 | 说明 | 类型 |
|-----|------|------|
| countNums | 数据总数 | String |
| countPages | 总页数 | String |
| curPage | 当前页 | String |
| specialId | 专题ID | String |
| bindingId | 专题绑定ID | String |
| specialName | 专题名称 | String |
| englishName | 英文名称 | String |
| brief | 简介 | String |
| backgroundPoster | 背景海报图 | String |
| posterThumbnail1/2/3 | 海报缩图1/2/3 | String |
| showSpecialName | 是否显示专题名(0否/1是) | String |
| specialType | 专题类型(1列表/2WEB/3LIVESHOW/4模板) | String |
| externalURL | 外链地址 | String |
| layoutMode | 排列模式(1横版/2竖版) | String |
| episodeShowType | 展示方式(1名称+海报/2名称/3海报) | String |
| playType | 播放类型(auto/single/cycle) | String |
| templateDatas[] | 同4.1结构的推荐位数据 | - |

---

### 3.7 获取频道首页导航接口 (4.5 channelList)

**路径:** /IPTV_EPG/TerminalUI/channelList

**功能:** 获取频道首页导航数据。instanceId为空时输出首层导航；非空时输出该首层导航下的所有二级导航。

**返回结构:** 同4.1的 templateDatas[] 结构

---

### 3.8 获取首层导航列表接口 (4.6 guidePlusList)

**路径:** /IPTV_EPG/TerminalUI/guidePlusList

**功能:** 获取首层导航列表，支持多模式(标准/少儿/老年/教育)和多样式(标准/沉浸式)。

**返回结构:** 同4.1的 templateDatas[] 结构，但 datas[] 中增加 channelMode 字段

---

## 四、行为动作体系 (36种)

| 序号 | 动作标识 | 功能描述 | 核心参数 |
|-----|---------|---------|---------|
| 1 | m_open_web | 全屏打开WEB页面 | webUrl |
| 2 | m_open_detail_page | 打开视频详情页 | videoId/videoType/programId |
| 3 | m_open_video_rank_page | 打开排行榜 | - |
| 4 | m_open_asset_category_page | 打开点播栏目列表 | - |
| 5 | m_open_player | 打开播放器 | videoId/videoType(0点播1直播2节目单)/beginTime/timeLen |
| 6 | m_open_tstv_page | 打开直播展示界面 | - |
| 7 | m_open_playbill_page | 打开回看 | - |
| 8 | m_open_app | 打开第三方APP | appPackage/appName/version/downloadUrl/md5/appCode |
| 9 | m_open_special_page | 打开专题页面 | specialId |
| 10 | m_open_star_detail_page | 打开明星详情 | starId |
| 11 | m_open_playlist_page | 播放记录 | - |
| 12 | m_open_collect_page | 我的收藏 | - |
| 13 | m_open_search_page | 搜索页面 | - |
| 14 | m_open_message_system | 消息系统 | - |
| 15 | m_open_home_mimi_page | 切换版本 | - |
| 16 | m_no_action | 占位符 | - |
| 17 | m_open_template_data_page | 打开模板页面 | bindTemplateId/bindInstanceId |
| 18 | m_open_template_data | 绑定模板数据 | bindTemplateId/bindInstanceId |
| 19 | m_to_top | 回到顶部 | - |
| 20 | m_small_auto_play | 小视频自动播放 | videoId/videoType/rootCategoryId/categoryId |
| 21 | m_small_selected_play | 小视频选中播放 | 同上 |
| 22 | m_open_mgtv_app | 打开芒果TV APP | appPackage/etc |
| 23 | m_open_detail_program_page | (已废除) | - |
| 24 | m_open_recommend_data | 绑定智能推荐 | - |
| 25 | m_open_setting | 设置界面 | - |
| 26 | m_open_wode | 打开我的 | - |
| 27 | m_open_wode_layer2 | 我的二级页面 | - |
| 28 | m_open_playlist | 我的播单 | - |
| 29 | m_open_member_pianku | 会员片库 | - |
| 30 | m_open_nine_screens | 九屏同看 | - |
| 31 | m_open_live_collect | 直播收藏 | - |
| 32 | m_open_feedback_list_page | 问题反馈 | - |
| 33 | m_open_exchange_card | 兑换码 | - |
| 34 | m_open_WeChat | 绑定微信 | - |
| 35 | m_open_about_us | 关于我们 | - |
| 36 | m_open_specialchannel_page | 专题频道 | - |

---

## 五、接口数据流

```
终端启动 → 1.1 EPGIndex(获取所有URL基地址+下行参数)
          → 1.2 GetAbilityVersion(能力版本号+地区码+用户模式)
          → 1.3 SyncTime(时钟同步)
          → 4.1 GetInitMetaData(UI初始化,模板+推荐位+行为动作)
          → 4.2 GetPublicImage(UI公共图片资源)
          → 4.3 GetSubChannelData(专题详情)
          → 4.5 channelList(频道导航,instanceId控制层级)
          → 4.6 guidePlusList(首层导航,多模式/多样式)
```

---

## 六、响应字段与动态解析对照要点

当使用动态解析工具解析真实响应时，字段路径映射关系:

| API文档字段路径 | JSON实际路径 | 说明 |
|---------------|-------------|------|
| templateDatas/datas/dataId | templateDatas[].datas[].dataId | 推荐位数据ID |
| templateDatas/datas/defaultActions/action | templateDatas[].datas[].defaultActions.action | 行为动作 |
| templateDatas/datas/defaultActions/bindTemplateName | templateDatas[].datas[].defaultActions.bindTemplateName | 绑定模板名 |
| templateDatas/datas/extendProperties/exKey | templateDatas[].datas[].extendProperties[].exKey | 扩展属性KEY |
| templateDatas/datas/defaultTemlpateData/datas[].defaultActions | templateDatas[].datas[].defaultTemlpateData.datas[].defaultActions | 二级模板的动作 |
| templateDatas/datas/defaultTemlpateData/offset_menta_data/ | templateDatas[].datas[].defaultTemlpateData.offset_menta_data | 推荐位偏移上报 |

---

## 七、河南移动业务跳转能力（参考《河南移动业务配置》第5点）

> 来源：D:\工作\知识库code\Library\Clippings\河南移动业务配置 - 智慧大屏 - 大芒果仓库.md

### 7.1 河南移动通用跳转 (m_open_henanyd_app)

**用途:** 打开河南移动第三方 App，未安装时下载安装后打开。

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| appPackage | 是 | 目标 App 包名 |
| downloadUrl | 按业务需要 | APK 下载链接，未安装目标 App 时使用 |
| appAction | 按业务需要 | 打开目标 App 时使用的 action |
| exInfo | 否 | 跳转时传给目标 App 的附加参数 |
| webUrl | 待确认 | 收银台场景可能使用（先跳亚信 APK 再拉起 WebView） |

downloadUrl 支持追加特殊参数：`mgSenseType`（应用安装感知类型，默认0）、`mgAppCode`（应用唯一标识，默认取 appPackage hash）。

### 7.2 聚焦行为跳转 (m_open_henanyd_app_auto)

**用途:** 焦点落到内容位时自动触发的播放/展示行为。河南移动直播内容必须配置。

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| videoType | 是 | 视频类型，0=点播，1=直播 |
| videoId | 是 | 分集 ID |
| programId | 否 | 合集 ID |
| playUrl | 否 | 直播流地址，配置后替换下行默认直播流并在首页通栏播放 |
| exData | 否 | 额外业务参数，如 playType=1;contentType=1;businessType=1;tid=-1;idflag=1 |

### 7.3 第三方视频播放页跳转 (m_open_play_other_full_clean_video)

**用途:** 打开第三方视频播放页并全屏播放。

| 参数 | 是否必填 | 说明 |
| --- | --- | --- |
| name | 是 | 视频标题 |
| playUrl | 是 | 第三方视频播放地址 |

### 7.4 前端动作语义词典（已实现于 capture.html）

上述三种动作已结构化录入 capture.html 的 _HENAN_ACTION_DEFS，抓包页坑位明细会自动展示：
- 动作名 + 中文语义 + 文档出处（5.1/5.2/5.3）
- 关键参数按 keys 顺序列出：有值 → 绿色高亮标签；未配置 → 灰色虚线标签
- 鼠标悬停参数标签显示中文说明

---

## 八、Skill 调用指南

### 8.1 Skill 文件位置

    D:\WorkCode\AdbTool-maste\src\capture\EPG_API_SKILL.md

### 8.2 何时调用本 Skill

遇到以下场景时先读取本文件：

| 场景 | 读取章节 |
|------|---------|
| 解析 IPTV 智慧大屏任意 EPG 接口响应/请求 | 第一~六章 |
| 识别行为动作 action 的中文语义 | 第四章（36种）+ 第七章（河南移动3种） |
| 需要知道接口路径/参数/返回结构 | 第三章各接口明细 |
| 动态解析响应字段（生成字段结构表） | 第六章对照要点 |
| 开发/调试 capture.html 的模板结构解析 | 第七章 7.4 |

### 8.3 调用方式（告知 AI 的一句话模板）

**方式A：完整加载**
> 请先读取 D:\WorkCode\AdbTool-maste\src\capture\EPG_API_SKILL.md，然后分析这个接口/响应：[粘贴接口URL或JSON]

**方式B：定向查接口**
> 查一下 EPG_API_SKILL.md 里 [接口名或编号] 的请求参数和返回结构

**方式C：识别 action**
> 参考 EPG_API_SKILL.md 第四章和第七章，解释这个 action=[动作名] 的含义和参数

**方式D：结合抓包页开发**
> 结合 EPG_API_SKILL.md 和 capture.html 的模板结构动态解析，帮我 [具体需求]

### 8.4 补充知识时的约定

- 新接口文档 → 按第三章的格式追加到 Skill 文件
- 新 action → 同步更新第四章表格 + capture.html 的 _ACTION_MEANING / _HENAN_ACTION_DEFS
- 新业务配置（如本文件第七章）→ 在第六章后追加新章节

---
