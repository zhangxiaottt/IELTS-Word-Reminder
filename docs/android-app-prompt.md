# 雅思单词复习 Android App —— 开发需求提示词

> 把下面整段复制给你的 Android 开发 AI（Cursor / Trae / GPT / Claude 都行）。

---

## 0. 角色

你是一名资深 Android 开发工程师。请用 **Kotlin + Jetpack Compose** 从零实现一个原生 Android App，名字叫 **IELTS Review**，用于在手机上复习雅思单词。后端已经由我（用户）写好，你只需要写 App 端。

**核心架构要求：手机端是"本地优先"的——** App 内置 Room (SQLite) 数据库，所有浏览、复习、查询功能**离线也能用**；只有在需要"同步"（从电脑拉新词、把手机上的复习标记写回电脑）时才走网络。电脑端是主录入端，手机端是复习+偶尔录入端。

## 1. 技术栈（硬性要求）

- Kotlin，minSdk 26（Android 8.0），targetSdk 34
- Jetpack Compose（Material 3）
- 单 Activity + Navigation Compose
- MVVM：ViewModel + StateFlow
- 网络：Retrofit 2 + OkHttp 4 + kotlinx.serialization（或 Gson，二选一）
- 本地数据库：Room (SQLite)，实体 `WordEntity`、`ArticleEntity`，Dao 提供 Flow 观察
- 本地持久化：DataStore Preferences（存服务器地址、上次同步时间等）
- 协程 + lifecycleScope，同步任务用 WorkManager 或 CoroutineWorker
- 包名：`com.ielts.review`
- 竖屏强制，不支持横屏

## 2. 后端 API 约定（**必须严格按这个对接**）

### 2.1 通用约定

- 基础 URL 在 App 内可配置（设置页填，默认 `http://192.168.1.100:21001`）
- 所有请求和响应都是 `application/json; charset=utf-8`
- 成功响应：`{"code":0,"data":...}`
- 失败响应：`{"code":1,"msg":"错误信息"}`
- 解析时统一判断 `code == 0` 才算成功，否则弹 toast 显示 `msg`
- 后端是我自己写的 Java HttpServer，**没有跨域问题**（App 不是浏览器），但**必须在设置页允许用户改 baseUrl**，因为我电脑的局域网 IP 会变

### 2.2 离线架构与同步策略（**最重要，别写错**）

**手机端 Room 数据库的表：**

```kotlin
@Entity
data class WordEntity(
  @PrimaryKey val id: Long,       // 以后端 id 为准；手机端新建的词在 POST 成功后拿回后端 id
  val word: String,
  val phonetic: String,
  val meaning: String,
  val example: String,
  val familiar: Int,              // 0-100
  val reviewCount: Int,
  val createdAt: String,
  val lastReview: String,
  val dirty: Boolean = false,     // true = 本地有未同步到后端的修改
  val deletedLocally: Boolean = false
)
```

**同步规则：**

1. **启动时**：如果有网，后台调 `GET /api/words` 拉全量列表（单词量级几百到几千，一次性拉完），写入 Room，用 `id` 冲突时**后端数据覆盖本地**（但本地 `dirty=true` 的字段除外——详见第 4 条）。
2. **下拉刷新**：同启动同步，用户手动触发。
3. **复习时（点认识/不认识）**：
   - 先立刻更新 Room 里的 `familiar` 和 `reviewCount`、`lastReview`，UI 立刻切下一张（**不阻塞**）
   - 然后异步调 `POST /api/words/{id}/familiar`
   - 网络失败：把这条记录标成 `dirty=true`，下次有网时自动重试
4. **手机端录入单词**：
   - 先调 `POST /api/words`，成功后用后端返回的 id 写入 Room
   - 网络失败：存一条 `dirty=true` 的本地记录（id 用负数临时 id，比如 `-System.currentTimeMillis()`），下次有网时补 POST
5. **手机端改释义/删词**：同上，先写本地，再异步同步；失败就 dirty。
6. **有网时**：App 切到前台时自动检查未同步队列（`dirty=true` 的记录），批量发往后端，成功后清 dirty。
7. **离线时**：所有页面照常工作，只是顶部显示一个小的离线提示条"当前离线，数据来自本地缓存"。

**UI 取数规则：**

- 所有列表/卡片/复习页都**从 Room 读**（用 Flow 观察），不要直接从内存/网络读
- 网络请求只用于"同步"，不用于"展示"——这样断网时 App 完全可用

### 2.3 数据模型 Word

```json
{
  "id": 12,
  "word": "ubiquitous",
  "phonetic": "/juːˈbɪkwɪtəs/",
  "meaning": "adj. 无处不在的",
  "example": "Smartphones have become ubiquitous.",
  "familiar": 35,
  "review_count": 4,
  "created_at": "2026-11-01 20:30:00",
  "last_review": "2026-11-04 08:12:00"
}
```

字段说明：
- `familiar`：0-100 的熟悉度，越高越熟
- `review_count`：复习次数
- 所有字符串字段都可能是空串 `""`，UI 上要兜底显示 "-"

### 2.4 接口列表

| Method | Path | 入参 | 返回 data |
|---|---|---|---|
| GET | `/api/health` | 无 | `{"status":"ok","port":21001}` |
| GET | `/api/words` | query: `keyword`, `date_from`, `date_to`（都可选，格式 `YYYY-MM-DD`） | `Word[]` |
| GET | `/api/words/random` | query: `limit=20`, `max_familiar=60` | `Word[]` |
| POST | `/api/words` | body: `{word, phonetic, meaning, example}` | 新建的 Word |
| PUT | `/api/words/{id}` | body: 同上四字段（可选） | `true/false` |
| DELETE | `/api/words/{id}` | 无 | `true/false` |
| POST | `/api/words/{id}/familiar` | body: `{"known":true}` 或 `{"known":false}` | `true/false` |
| GET | `/api/dict` | query: `word=xxx` | `{phonetic, meaning, example}`（查不到时可能是空字符串） |
| GET | `/api/article` | query: `date=YYYY-MM-DD` | `{date, title, content}`（无文章时返回 `{}`） |
| POST | `/api/article/generate` | body: `{date, days:3, limit:12}` | 同 `/api/article` |

## 3. 页面结构（底部三个 Tab）

### Tab 1：今日复习（默认首页）

- 进入时调 `GET /api/words/random?limit=20&max_familiar=60`，取熟悉度 ≤ 60 的 20 个词
- 大卡片式：一次只显示一个单词
  - 上半部分：**英文单词**（大字、粗体）
  - 中间：音标（灰色小字，可空）
  - 下半部分默认**隐藏**释义和例句，点一下卡片翻面显示（或加一个"显示释义"按钮）
- 底部两个大按钮：
  - **不认识**（红色/灰色）：调 `POST /api/words/{id}/familiar {"known":false}`，然后切下一张
  - **认识**（绿色）：调 `POST /api/words/{id}/familiar {"known":true}`，然后切下一张
- 顶部显示进度：`第 3 / 20 张`，带一个细进度条
- 全部 20 张看完后显示一个完成页："今天复习完成 🎉" + 一个"再来一轮"按钮
- 卡片切换要带简单动画（淡入淡出或横向滑动）

### Tab 2：单词本

- 顶部搜索框：输入关键字实时调 `GET /api/words?keyword=xxx`
- 列表：每行显示 word（粗体）+ meaning（灰色一行截断）+ familiar 进度条
- 点击某行进入详情页：
  - 完整显示 word / phonetic / meaning / example
  - 显示 familiar 数值、review_count、created_at
  - 两个按钮：编辑（弹窗可改 meaning/example）、删除（确认后调 DELETE）
- 下拉刷新

### Tab 3：录入单词

- 一个输入框："输入英文单词，回车查询"
- 输入完失焦或点"查询释义"按钮：调 `GET /api/dict?word=xxx`
- 下方三个可编辑文本框自动填入：
  - 音标（只读，来自 API）
  - 中文释义（可编辑）
  - 例句（可编辑）
- 底部"保存"按钮：调 `POST /api/words`
  - 成功：toast "已保存"，清空输入框，自动聚焦
  - 失败（code=1，msg="该单词已收录"）：弹确认框"该单词已收录，是否覆盖更新？"，确认后调 `PUT /api/words/{id}`（你需要先在列表里查 id，或者我后端后续补一个"按 word 查 id"的接口；现在你先按 word 搜一遍 `/api/words?keyword=xxx` 找完全匹配的）

### 额外页面：每日文章（从首页顶部 banner 进入）

- 进入时调 `GET /api/article?date=今天`
- 如果返回空对象 `{}`，显示一个"生成今日文章"按钮，点击调 `POST /api/article/generate {date:今天, days:3, limit:12}`（注意：这个请求后端要调 LLM，可能要 10-30 秒，要显示 loading）
- 有文章后：标题（大字）+ 正文（可滚动）
- 正文里出现的雅思单词（从今天复习的 20 个词里匹配）要高亮显示（比如主色调 #4A90E2）

### 设置页（右上角齿轮图标进入）

- 服务器地址输入框（默认 `http://192.168.1.100:21001`）
- "测试连接"按钮：调 `GET /api/health`，成功显示"连接成功，端口 xxx"，失败显示具体错误
- 保存到 DataStore，下次启动自动读取
- 显示 App 版本号

## 4. UI 风格

- Material 3 亮色主题，主色调 `#4A90E2`（淡蓝），背景白色
- 字体：默认 Sans-Serif，英文单词用更大字号粗体
- 所有按钮最小高度 48dp，适合单手操作
- 圆角卡片 16dp，8dp 边距
- 不要求花哨动画，干净清爽就行
- 不需要深色模式（第一版只做亮色）

## 5. 工程结构建议

```
app/src/main/java/com/ielts/review/
├── IeltsApp.kt                  # Application + 初始化 Room
├── MainActivity.kt              # 单 Activity
├── data/
│   ├── local/
│   │   ├── AppDatabase.kt       # Room 数据库
│   │   ├── WordDao.kt
│   │   ├── WordEntity.kt
│   │   └── ArticleEntity.kt
│   ├── remote/
│   │   ├── ApiService.kt        # Retrofit 接口
│   │   ├── WordDto.kt           # 后端 JSON 模型
│   │   └── ApiClient.kt         # Retrofit 单例，baseUrl 动态
│   ├── SyncRepository.kt        # 同步逻辑：拉全量、上传 dirty 队列
│   ├── WordRepository.kt        # 统一入口：读走 Room，写走 Room+同步
│   └── SettingsRepository.kt    # DataStore
├── ui/
│   ├── review/ReviewScreen.kt + ReviewViewModel.kt
│   ├── library/LibraryScreen.kt + LibraryViewModel.kt
│   ├── detail/WordDetailScreen.kt
│   ├── input/InputScreen.kt + InputViewModel.kt
│   ├── article/ArticleScreen.kt
│   ├── settings/SettingsScreen.kt
│   └── theme/                  # Material3 配色
└── nav/AppNavigation.kt
```

## 6. 异常与边界（必须处理）

- **离线是常态，不是错误**：所有页面从 Room 读数据，断网时正常显示内容，顶部只显示一个小的灰色提示条"当前离线，数据来自本地缓存"，不要弹错误、不要跳转设置
- 主动同步（下拉刷新、点设置页"测试连接"）失败时才弹 toast "无法连接到服务器"
- 后端返回 `code=1`：toast 显示 msg
- 单词字段为空串：UI 显示 "-" 而不是崩溃
- 本地数据库为空（第一次安装、从未同步过）：显示"还没有同步过单词，请到设置页填写服务器地址后下拉刷新" + 跳转设置
- loading 状态：同步期间显示一个小圆环，不能白屏
- 请求超时设 10 秒，文章生成请求超时设 60 秒
- 未同步队列（dirty=true 的记录）在设置页显示一个数字"待同步 N 条"，方便用户排查

## 7. 我需要你交付的东西

1. 完整可编译的 Android Studio 工程（Gradle 同步能过）
2. 包名 `com.ielts.review`，应用名显示为 "IELTS Review"
3. 一个能直接跑的 debug APK（如果你能 build 的话；不能就给我完整工程我自己 build）
4. 简短的 README：怎么改服务器地址、后端要开什么端口

## 8. 非需求（**第一版不要做**）

- 不要做用户登录/注册（单机用，直接连我自己的后端）
- 不要推送通知
- 不要暗黑模式
- 不要桌宠/动画小人
- 不要统计图表
- 不要国际化（只做简体中文 + 英文单词本身）
- 不要做冲突合并的复杂逻辑（比如两边同时改了同一个词的释义）：第一版规则简单点——**启动同步时后端覆盖本地非 dirty 字段；本地 dirty 字段在成功上传后以本地为准**。够了。

---

## 给用户（我自己）的备注

**使用前你需要做的两件事**：

1. **改 Java 后端的监听地址**：
   打开 `java-server/src/main/java/com/ielts/reminder/server/LocalServer.java` 第 66 行，把
   ```java
   server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);
   ```
   改成
   ```java
   server = HttpServer.create(new InetSocketAddress("0.0.0.0", port), 0);
   ```
   否则手机连不上（服务只听本机回环）。

2. **Windows 防火墙放行端口**：
   启动 Java 服务时，Windows 防火墙会弹提示，选"允许专用网络"。或者手动在防火墙入站规则加 TCP 21001。

3. **查电脑局域网 IP**：
   PowerShell 跑 `ipconfig`，找 WLAN 或以太网的 IPv4 地址（比如 `192.168.3.25`）。手机和电脑连同一个 WiFi，在 App 设置页填 `http://192.168.3.25:21001`。
