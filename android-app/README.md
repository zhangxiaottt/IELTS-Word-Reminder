# IELTS Review（Android 客户端）

一个配合 `java-server` 使用的本地单词复习 App：Kotlin + Jetpack Compose + Room + Retrofit。

- 包名：`com.ielts.review`
- minSdk 26 / targetSdk 34 / compileSdk 35
- 竖屏，单 Activity + Navigation Compose

## 功能

| 模块 | 说明 |
| --- | --- |
| 复习 | 取熟悉度 ≤ 60 的 20 个词，点击卡片翻面，认识 +20 / 不认识 -20，带进度条和滑动动画 |
| 单词本 | Room 本地列表 + 关键字搜索（本地 LIKE + 联网时并入后端搜索结果），下拉刷新，待同步词条角标 |
| 单词详情 | 查看音标/释义/例句/熟悉度，可编辑释义例句、删除（同步到电脑端） |
| 录入 | 输入单词 → 调 `/api/dict` 查释义 → 保存；重复词弹窗确认覆盖 |
| 每日文章 | `/api/article` 读取当天文章并缓存；没有时请求生成（60 秒超时）；复习词在正文中高亮 |
| 设置 | 服务器地址、测试连接、待同步条数、上次同步时间、版本号 |

## 离线优先策略

- 所有列表（复习、单词本、详情、文章）都从 Room 读取，断网照常浏览。
- 写操作先写本地：
  - 在线录入：先 `POST`，成功后用后端 id 落库。
  - 离线录入：生成负数临时 id，`dirty = true`，联网后补传。
  - 复习点认识/不认识：本地立即生效，联网时 `POST /api/words/{id}/familiar`；失败保留 `pendingKnown` 供下次重放。
  - 删除：本地标记 `deletedLocally`，联网时 `DELETE`。
- 全量同步：先推 dirty 队列，再拉 `/api/words`；后端覆盖本地非 dirty 记录，dirty 记录保留本地修改。
- 触发时机：App 启动 / 回到前台（WorkManager 一次性任务）、每 6 小时周期任务、单词本下拉刷新、复习页进入时拉随机词。

## 后端要求

1. Java 服务监听 `0.0.0.0`（`LocalServer.java` 中 `HttpServer.create(new InetSocketAddress("0.0.0.0", port), 0)`）。
2. 手机与电脑连接同一 Wi-Fi。
3. 设置页填写电脑局域网 IP，例如 `http://192.168.1.100:21001`（默认值见 `ApiClient.DEFAULT_BASE_URL`）。
4. 明文 HTTP 已在 Manifest 中开启 `android:usesCleartextTraffic="true"`。

用到的接口：

```
GET  /api/health
GET  /api/words?keyword=
GET  /api/words/random?limit=20&max_familiar=60
POST /api/words
PUT  /api/words/{id}
DELETE /api/words/{id}
POST /api/words/{id}/familiar
GET  /api/dict?word=
GET  /api/article?date=yyyy-MM-dd
POST /api/article/generate
```

## 构建

环境要求：JDK 17 及以上（推荐 Android Studio 自带的 JBR / JDK 21），Android SDK Platform 35 + Build-Tools 35.0.0。

Android Studio：直接 `Open` 本目录，等待 Gradle Sync 后运行 `app`。

命令行：

```bash
# Windows
gradlew.bat assembleDebug

# macOS / Linux
./gradlew assembleDebug
```

产物：`app/build/outputs/apk/debug/app-debug.apk`

首次构建前在工程根目录创建 `local.properties`（Android Studio 会自动生成）：

```properties
sdk.dir=D\:\\Android\\Sdk
```

## 目录结构

```
app/src/main/java/com/ielts/review/
├── IeltsApp.kt                 Application + WorkManager 周期同步
├── MainActivity.kt             单 Activity，竖屏
├── data/
│   ├── AppContainer.kt         手动依赖注入
│   ├── SettingsRepository.kt   DataStore 保存服务器地址 / 上次同步时间
│   ├── NetworkMonitor.kt       ConnectivityManager 网络状态 Flow
│   ├── SyncRepository.kt       推拉同步、随机词/搜索合并
│   ├── WordRepository.kt       单词读写（离线优先）+ 同步触发
│   ├── ArticleRepository.kt    文章读取/生成 + 本地缓存
│   ├── local/                  Room Entity / DAO / Database
│   └── remote/                 Retrofit ApiService / DTO / ApiClient
├── ui/
│   ├── review/                 复习页
│   ├── library/                单词本
│   ├── detail/                 单词详情
│   ├── input/                  录入
│   ├── article/                每日文章
│   ├── settings/               设置
│   ├── common/                 离线提示条 / 空列表占位
│   └── theme/                  主题色与配色
├── nav/AppRoot.kt              导航 + 底部 Tab
└── work/SyncWorker.kt          CoroutineWorker 同步任务
```

## 备注

- Room 数据版本为 1，升级字段时请补 Migration（当前使用 `fallbackToDestructiveMigration()`）。
- 熟悉度规则：认识 +20、不认识 -20，范围 0-100；复习次数 +1，并记录最近复习时间。
- `ApiClient` 内置两套超时：普通请求 10 秒，文章生成 60 秒。
