package com.ielts.reminder.server;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.ielts.reminder.api.DictAPI;
import com.ielts.reminder.api.LLMClient;
import com.ielts.reminder.article.ArticleGenerator;
import com.ielts.reminder.config.ConfigManager;
import com.ielts.reminder.data.WordManager;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;

/**
 * 本地 REST 服务：Python 界面层通过 HTTP 调用 Java 服务层。
 *
 * 设计要点：
 * - 使用 JDK 内置 HttpServer，端口 21001（localhost 绑定，仅本机可访问）
 * - 统一响应格式：{ "code": 0, "data": ... } 成功；{ "code": 1, "msg": "..." } 失败
 * - 每个请求独立 try/catch，任何异常都转成 JSON 错误响应，绝不崩溃
 */
public class LocalServer {

    public static final int DEFAULT_PORT = 21001;

    private final ConfigManager config;
    private final WordManager wordManager;
    private final DictAPI dictApi;
    private final LLMClient llmClient;
    private final ArticleGenerator articleGenerator;
    private final Gson gson = new GsonBuilder().create();

    private HttpServer server;

    public LocalServer(ConfigManager config, WordManager wordManager,
                       DictAPI dictApi, LLMClient llmClient,
                       ArticleGenerator articleGenerator) {
        this.config = config;
        this.wordManager = wordManager;
        this.dictApi = dictApi;
        this.llmClient = llmClient;
        this.articleGenerator = articleGenerator;
    }

    /** 启动服务（端口被占用时自动向后顺延最多 5 个） */
    public void start() throws IOException {
        int port = DEFAULT_PORT;
        IOException last = null;
        for (int i = 0; i < 5; i++) {
            try {
                server = HttpServer.create(new InetSocketAddress("0.0.0.0", port), 0);
                server.setExecutor(Executors.newFixedThreadPool(4));
                server.createContext("/", this::dispatch);
                server.start();
                System.out.println("[LocalServer] 已启动: http://0.0.0.0:" + port + " （局域网同 WiFi 设备可访问）");
                return;
            } catch (IOException e) {
                last = e;
                port++;
            }
        }
        throw last != null ? last : new IOException("无法绑定端口");
    }

    /** 停止服务 */
    public void stop() {
        if (server != null) {
            server.stop(0);
            System.out.println("[LocalServer] 已停止");
        }
    }

    // ------------------------------------------------------------------ //
    // 路由分发
    // ------------------------------------------------------------------ //

    private void dispatch(HttpExchange ex) throws IOException {
        try {
            String method = ex.getRequestMethod();
            String path = ex.getRequestURI().getPath();
            String query = ex.getRequestURI().getRawQuery();

            // 匹配规则：method + 路径前缀
            if ("GET".equals(method) && path.equals("/api/health")) {
                sendJson(ex, 200, ok(Map.of("status", "ok", "port", getPort())));
            } else if ("POST".equals(method) && path.equals("/api/words")) {
                handleAddWord(ex);
            } else if ("GET".equals(method) && path.equals("/api/words")) {
                handleListWords(ex, query);
            } else if ("GET".equals(method) && path.equals("/api/words/random")) {
                handleRandomWords(ex, query);
            } else if ("PUT".equals(method) && path.matches("/api/words/\\d+")) {
                handleUpdateWord(ex, parseId(path));
            } else if ("DELETE".equals(method) && path.matches("/api/words/\\d+")) {
                handleDeleteWord(ex, parseId(path));
            } else if ("DELETE".equals(method) && path.equals("/api/words/batch")) {
                handleBatchDelete(ex);
            } else if ("GET".equals(method) && path.equals("/api/review/list")) {
                sendJson(ex, 200, ok(wordManager.getReviewWordList()));
            } else if ("POST".equals(method) && path.matches("/api/words/\\d+/familiar")) {
                handleMarkFamiliar(ex, parseId(path));
            } else if ("GET".equals(method) && path.equals("/api/dict")) {
                handleDict(ex, query);
            } else if ("GET".equals(method) && path.equals("/api/article")) {
                handleGetArticle(ex, query);
            } else if ("POST".equals(method) && path.equals("/api/article/generate")) {
                handleGenerateArticle(ex);
            } else if ("GET".equals(method) && path.equals("/api/llm/test")) {
                handleLlmTest(ex, query);
            } else if ("GET".equals(method) && path.equals("/api/config")) {
                sendJson(ex, 200, ok(config.getData()));
            } else if ("POST".equals(method) && path.equals("/api/config/set")) {
                handleConfigSet(ex);
            } else {
                sendJson(ex, 404, fail("接口不存在: " + method + " " + path));
            }
        } catch (Exception e) {
            // 全局兜底：任何异常都转成 JSON 错误，不让连接异常断开
            try {
                sendJson(ex, 500, fail("服务内部错误: " + e.getMessage()));
            } catch (IOException ignored) {
            }
        }
    }

    // ------------------------------------------------------------------ //
    // 各业务接口
    // ------------------------------------------------------------------ //

    /** 录入单词：POST /api/words {word, phonetic, meaning, example} */
    private void handleAddWord(HttpExchange ex) throws IOException {
        JsonObject body = readJson(ex);
        String word = optStr(body, "word");
        boolean existed = wordManager.getWordByWord(word) != null;
        boolean ok = wordManager.addWord(word, optStr(body, "phonetic"),
                optStr(body, "meaning"), optStr(body, "example"));
        if (!ok) {
            sendJson(ex, 200, existed ? fail("该单词已收录") : fail("录入失败"));
            return;
        }
        Map<String, Object> row = wordManager.getWordByWord(word);
        sendJson(ex, 200, ok(row));
    }

    /** 列表：GET /api/words?keyword=&date_from=&date_to= */
    private void handleListWords(HttpExchange ex, String query) throws IOException {
        Map<String, String> q = parseQuery(query);
        sendJson(ex, 200, ok(wordManager.getAllWords(
                q.get("keyword"), q.get("date_from"), q.get("date_to"))));
    }

    /** 随机取词：GET /api/words/random?limit=&max_familiar= */
    private void handleRandomWords(HttpExchange ex, String query) throws IOException {
        Map<String, String> q = parseQuery(query);
        int limit = parseInt(q.get("limit"), 10);
        int maxFamiliar = parseInt(q.get("max_familiar"), 100);
        sendJson(ex, 200, ok(wordManager.getRandomWords(limit, maxFamiliar)));
    }

    /** 修改单词：PUT /api/words/{id} */
    private void handleUpdateWord(HttpExchange ex, long id) throws IOException {
        JsonObject body = readJson(ex);
        Map<String, Object> data = new LinkedHashMap<>();
        for (String key : List.of("word", "phonetic", "meaning", "example")) {
            if (body.has(key)) {
                data.put(key, optStr(body, key));
            }
        }
        sendJson(ex, 200, ok(wordManager.updateWord(id, data)));
    }

    /** 删除单词：DELETE /api/words/{id} */
    private void handleDeleteWord(HttpExchange ex, long id) throws IOException {
        sendJson(ex, 200, ok(wordManager.deleteWord(id)));
    }

    /** 批量删除：DELETE /api/words/batch {ids:[...]} */
    private void handleBatchDelete(HttpExchange ex) throws IOException {
        JsonObject body = readJson(ex);
        JsonArray arr = body.getAsJsonArray("ids");
        List<Long> ids = new ArrayList<>();
        if (arr != null) {
            for (JsonElement e : arr) {
                ids.add(e.getAsLong());
            }
        }
        sendJson(ex, 200, ok(wordManager.deleteWords(ids)));
    }

    /** 标记认识/不认识：POST /api/words/{id}/familiar {known:true|false} */
    private void handleMarkFamiliar(HttpExchange ex, long id) throws IOException {
        JsonObject body = readJson(ex);
        boolean known = body.has("known") && body.get("known").getAsBoolean();
        sendJson(ex, 200, ok(wordManager.markFamiliar(id, known)));
    }

    /** 词典查询：GET /api/dict?word= */
    private void handleDict(HttpExchange ex, String query) throws IOException {
        Map<String, String> q = parseQuery(query);
        String word = q.getOrDefault("word", "");
        sendJson(ex, 200, ok(dictApi.query(word)));
    }

    /** 读取某天文章：GET /api/article?date=YYYY-MM-DD */
    private void handleGetArticle(HttpExchange ex, String query) throws IOException {
        Map<String, String> q = parseQuery(query);
        String date = q.getOrDefault("date", "");
        Map<String, Object> art = articleGenerator.load(date);
        sendJson(ex, 200, ok(art == null ? Map.of() : art));
    }

    /** 生成/获取文章：POST /api/article/generate {date, seed, days, limit} */
    private void handleGenerateArticle(HttpExchange ex) throws IOException {
        JsonObject body = readJson(ex);
        String date = body.has("date") && !body.get("date").isJsonNull()
                ? body.get("date").getAsString() : null;
        String seed = body.has("seed") && !body.get("seed").isJsonNull()
                ? body.get("seed").getAsString() : null;
        int days = body.has("days") ? body.get("days").getAsInt() : 3;
        int limit = body.has("limit") ? body.get("limit").getAsInt() : 12;
        Map<String, Object> art = articleGenerator.getOrGenerate(date, seed, days, limit);
        sendJson(ex, 200, ok(art));
    }

    /** 测试大模型连接：GET /api/llm/test?base_url=&api_key=&model= */
    private void handleLlmTest(HttpExchange ex, String query) throws IOException {
        Map<String, String> q = parseQuery(query);
        Map.Entry<Boolean, String> result = llmClient.testConnection(
                q.get("base_url"), q.get("api_key"), q.get("model"));
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("ok", result.getKey());
        data.put("message", result.getValue());
        sendJson(ex, 200, ok(data));
    }

    /** 写配置：POST /api/config/set {key:"panel.opacity", value:0.9} */
    private void handleConfigSet(HttpExchange ex) throws IOException {
        JsonObject body = readJson(ex);
        String key = optStr(body, "key");
        JsonElement value = body.get("value");
        if (key.isEmpty() || value == null || value.isJsonNull()) {
            sendJson(ex, 200, fail("缺少 key 或 value"));
            return;
        }
        Object v;
        if (value.isJsonPrimitive()) {
            var prim = value.getAsJsonPrimitive();
            if (prim.isBoolean()) {
                v = prim.getAsBoolean();
            } else if (prim.isNumber()) {
                double d = prim.getAsDouble();
                v = (d == Math.floor(d) && !Double.isInfinite(d)) ? (int) d : d;
            } else {
                v = prim.getAsString();
            }
        } else {
            v = gson.fromJson(value, Object.class);
        }
        config.set(key, v);
        boolean saved = config.save();
        sendJson(ex, 200, ok(saved));
    }

    // ------------------------------------------------------------------ //
    // HTTP 工具
    // ------------------------------------------------------------------ //

    /** 当前实际监听的端口（测试用） */
    public int getPort() {
        return server == null ? -1 : server.getAddress().getPort();
    }

    /** 读取请求体并解析为 JSON 对象（空体返回空对象） */
    private JsonObject readJson(HttpExchange ex) throws IOException {
        try (InputStream in = ex.getRequestBody()) {
            byte[] bytes = in.readAllBytes();
            if (bytes.length == 0) {
                return new JsonObject();
            }
            JsonElement el = JsonParser.parseString(new String(bytes, StandardCharsets.UTF_8));
            return el.isJsonObject() ? el.getAsJsonObject() : new JsonObject();
        } catch (Exception e) {
            return new JsonObject();
        }
    }

    /** 解析 query string 为 Map（自动 URL 解码） */
    private static Map<String, String> parseQuery(String query) {
        Map<String, String> map = new LinkedHashMap<>();
        if (query == null || query.isEmpty()) {
            return map;
        }
        for (String pair : query.split("&")) {
            int idx = pair.indexOf('=');
            if (idx < 0) {
                continue;
            }
            String k = URLDecoder.decode(pair.substring(0, idx), StandardCharsets.UTF_8);
            String v = URLDecoder.decode(pair.substring(idx + 1), StandardCharsets.UTF_8);
            map.put(k, v);
        }
        return map;
    }

    /** 从路径尾部解析 id：/api/words/123 -> 123 */
    private static long parseId(String path) {
        String[] seg = path.split("/");
        try {
            return Long.parseLong(seg[seg.length - 1]);
        } catch (Exception e) {
            return -1;
        }
    }

    /** 成功响应包装 */
    private Map<String, Object> ok(Object data) {
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("code", 0);
        r.put("data", data);
        return r;
    }

    /** 失败响应包装 */
    private static Map<String, Object> fail(String msg) {
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("code", 1);
        r.put("msg", msg);
        return r;
    }

    /** 输出 JSON 响应 */
    private void sendJson(HttpExchange ex, int status, Object payload) throws IOException {
        byte[] bytes = gson.toJson(payload).getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static String optStr(JsonObject obj, String key) {
        JsonElement el = obj.get(key);
        if (el == null || el.isJsonNull()) {
            return "";
        }
        return el.getAsString();
    }

    private static int parseInt(String s, int def) {
        try {
            return Integer.parseInt(s);
        } catch (Exception e) {
            return def;
        }
    }
}
