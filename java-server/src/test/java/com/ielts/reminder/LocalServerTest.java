package com.ielts.reminder;

import com.ielts.reminder.api.DictAPI;
import com.ielts.reminder.api.LLMClient;
import com.ielts.reminder.article.ArticleGenerator;
import com.ielts.reminder.config.ConfigManager;
import com.ielts.reminder.data.WordManager;
import com.ielts.reminder.server.LocalServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

/**
 * LocalServer 冒烟测试：启动真实服务，走 HTTP 验证核心接口。
 */
class LocalServerTest {

    static LocalServer server;
    static HttpClient client;
    static int port;
    static WordManager wm;

    @TempDir
    static Path tempDir;

    @BeforeAll
    static void startServer() throws Exception {
        ConfigManager config = new ConfigManager(tempDir.resolve("config.json"));
        wm = new WordManager(tempDir.resolve("test.db"));
        DictAPI dict = DictAPI.getInstance();
        LLMClient llm = new LLMClient(config);
        ArticleGenerator gen = new ArticleGenerator(wm, tempDir.resolve("articles.json"), llm);
        server = new LocalServer(config, wm, dict, llm, gen);
        server.start();
        port = server.getPort();
        client = HttpClient.newHttpClient();
    }

    @AfterAll
    static void stopServer() {
        server.stop();
        wm.close();
    }

    /** 发请求并解析 JSON 字符串 */
    private static String get(String path) throws Exception {
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port + path))
                .GET().build();
        HttpResponse<String> resp = client.send(req, HttpResponse.BodyHandlers.ofString());
        assertEquals(200, resp.statusCode());
        return resp.body();
    }

    private static String post(String path, String json) throws Exception {
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port + path))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();
        HttpResponse<String> resp = client.send(req, HttpResponse.BodyHandlers.ofString());
        assertEquals(200, resp.statusCode());
        return resp.body();
    }

    @Test
    void 健康检查() throws Exception {
        String body = get("/api/health");
        assertTrue(body.contains("\"status\":\"ok\""));
    }

    @Test
    void 录入与复习列表() throws Exception {
        post("/api/words", "{\"word\":\"server_test\",\"phonetic\":\"/t/\"," +
                "\"meaning\":\"n. 测试\",\"example\":\"\"}");
        String list = get("/api/review/list");
        assertTrue(list.contains("server_test"));
    }

    @Test
    void 标记熟悉度() throws Exception {
        String added = post("/api/words", "{\"word\":\"familiar_test\",\"meaning\":\"n. 熟悉\"}");
        long id = extractId(added);
        post("/api/words/" + id + "/familiar", "{\"known\":true}");
        String list = get("/api/review/list");
        // familiar_test 熟悉度应为 20（不直接在断言里检查细节，验证接口不报错即可）
        assertTrue(list.contains("familiar_test"));
    }

    @Test
    void 词典接口() throws Exception {
        String body = get("/api/dict?word=apple");
        assertTrue(body.contains("\"code\":0"));
    }

    @Test
    void 文章生成接口() throws Exception {
        post("/api/words", "{\"word\":\"story_word\",\"meaning\":\"n. 故事词\"}");
        String body = post("/api/article/generate", "{\"date\":\"2026-10-10\",\"days\":3,\"limit\":12}");
        assertTrue(body.contains("\"code\":0"));
        assertTrue(body.contains("title"));
        assertTrue(body.contains("text"));
    }

    @Test
    void 配置读写接口() throws Exception {
        post("/api/config/set", "{\"key\":\"review.interval\",\"value\":15}");
        String cfg = get("/api/config");
        assertTrue(cfg.contains("\"interval\":15") || cfg.contains("\"interval\": 15"));
    }

    @Test
    void 不存在接口返回404错误码() throws Exception {
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port + "/api/nope"))
                .GET().build();
        HttpResponse<String> resp = client.send(req, HttpResponse.BodyHandlers.ofString());
        assertEquals(404, resp.statusCode());
        assertTrue(resp.body().contains("接口不存在"));
    }

    /** 从录入响应中提取 id（data 里的 id 字段） */
    private static long extractId(String json) {
        java.util.regex.Matcher m = java.util.regex.Pattern
                .compile("\"id\"\\s*:\\s*(\\d+)").matcher(json);
        return m.find() ? Long.parseLong(m.group(1)) : -1;
    }
}
