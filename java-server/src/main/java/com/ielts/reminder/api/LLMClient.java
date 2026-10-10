package com.ielts.reminder.api;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.ielts.reminder.config.ConfigManager;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 大模型 API 客户端（LLMClient）—— OpenAI 兼容、厂商无关。
 *
 * 候选厂商（DeepSeek / 豆包·火山方舟 / 通义千问 / 智谱 GLM 等）都提供
 * OpenAI 兼容的 POST {base_url}/chat/completions 接口，换厂商只需改
 * base_url / api_key / model 三项，代码零改动。
 *
 * 设计原则：
 * - 配置实时从 ConfigManager 读取，设置窗口改动即时生效（无需重启）
 * - 任何网络/解析异常都被捕获，对外返回 null 或 (false, 信息)，绝不崩溃
 */
public class LLMClient {

    /** 生成一篇短文要给足时间；网络失败等 15 秒即返回 */
    public static final Duration DEFAULT_TIMEOUT = Duration.ofSeconds(15);

    private final ConfigManager config;
    private final HttpClient client;

    public LLMClient(ConfigManager config) {
        this.config = config;
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
    }

    // ------------------------------------------------------------------ //
    // 配置读取
    // ------------------------------------------------------------------ //

    /** 返回当前生效的连接参数 */
    public Map<String, String> settings() {
        Map<String, String> s = new LinkedHashMap<>();
        s.put("enabled", String.valueOf(config.getBool("llm.enabled", false)));
        s.put("base_url", config.getString("llm.base_url", "").trim());
        s.put("api_key", config.getString("llm.api_key", "").trim());
        s.put("model", config.getString("llm.model", "").trim());
        return s;
    }

    /** 是否启用且参数齐全（启用 + 地址 + 密钥 + 模型名都非空） */
    public boolean enabled() {
        Map<String, String> s = settings();
        return Boolean.parseBoolean(s.get("enabled"))
                && !s.get("base_url").isEmpty()
                && !s.get("api_key").isEmpty()
                && !s.get("model").isEmpty();
    }

    // ------------------------------------------------------------------ //
    // 请求
    // ------------------------------------------------------------------ //

    /**
     * 执行一次 chat/completions 请求，返回助手文本。
     * 成功返回内容文本；任何异常返回 null（不抛异常）。
     */
    public String complete(List<Map<String, String>> messages, double temperature,
                           int maxTokens) {
        Map<String, String> s = settings();
        if (s.get("base_url").isEmpty() || s.get("api_key").isEmpty()
                || s.get("model").isEmpty()) {
            return null;
        }
        try {
            String url = s.get("base_url").replaceAll("/+$", "") + "/chat/completions";
            JsonObject payload = new JsonObject();
            payload.addProperty("model", s.get("model"));
            JsonArray msgs = new JsonArray();
            for (Map<String, String> m : messages) {
                JsonObject msg = new JsonObject();
                msg.addProperty("role", m.getOrDefault("role", "user"));
                msg.addProperty("content", m.getOrDefault("content", ""));
                msgs.add(msg);
            }
            payload.add("messages", msgs);
            payload.addProperty("temperature", temperature);
            payload.addProperty("max_tokens", maxTokens);

            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(DEFAULT_TIMEOUT)
                    .header("Authorization", "Bearer " + s.get("api_key"))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(payload.toString()))
                    .build();

            HttpResponse<String> resp = client.send(req,
                    HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() / 100 != 2) {
                return null;
            }
            JsonObject data = JsonParser.parseString(resp.body()).getAsJsonObject();
            String content = data.getAsJsonArray("choices").get(0)
                    .getAsJsonObject().getAsJsonObject("message")
                    .get("content").getAsString();
            return (content == null || content.isEmpty()) ? null : content;
        } catch (Exception e) {
            return null;
        }
    }

    /** 便捷：默认参数调用（temperature=0.7, maxTokens=800） */
    public String complete(List<Map<String, String>> messages) {
        return complete(messages, 0.7, 800);
    }

    // ------------------------------------------------------------------ //
    // 连接测试（供设置窗口「测试连接」使用）
    // ------------------------------------------------------------------ //

    /** 用给定参数（或当前配置）发一条极简消息，返回 (成功?, 提示文本) */
    public Map.Entry<Boolean, String> testConnection(String baseUrl, String apiKey,
                                                     String model) {
        String b = baseUrl != null ? baseUrl.trim() : settings().get("base_url");
        String k = apiKey != null ? apiKey.trim() : settings().get("api_key");
        String m = model != null ? model.trim() : settings().get("model");
        if (b.isEmpty() || k.isEmpty() || m.isEmpty()) {
            return Map.entry(false, "请先填写接口地址 / API Key / 模型名");
        }
        try {
            String url = b.replaceAll("/+$", "") + "/chat/completions";
            JsonObject payload = new JsonObject();
            payload.addProperty("model", m);
            JsonArray msgs = new JsonArray();
            JsonObject msg = new JsonObject();
            msg.addProperty("role", "user");
            msg.addProperty("content", "只回复两个字：正常");
            msgs.add(msg);
            payload.add("messages", msgs);
            payload.addProperty("temperature", 0);
            payload.addProperty("max_tokens", 10);

            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(DEFAULT_TIMEOUT)
                    .header("Authorization", "Bearer " + k)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(payload.toString()))
                    .build();
            HttpResponse<String> resp = client.send(req,
                    HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() / 100 != 2) {
                return Map.entry(false, "连接失败：HTTP " + resp.statusCode());
            }
            JsonObject data = JsonParser.parseString(resp.body()).getAsJsonObject();
            String text = data.getAsJsonArray("choices").get(0)
                    .getAsJsonObject().getAsJsonObject("message")
                    .get("content").getAsString();
            if (text == null || text.trim().isEmpty()) {
                // 能连上但模型无返回：多半是模型名填错
                return Map.entry(false, "连接成功但模型无返回，请检查模型名"
                        + "（DeepSeek 请填 deepseek-chat）");
            }
            String snippet = text.trim();
            if (snippet.length() > 20) {
                snippet = snippet.substring(0, 20);
            }
            return Map.entry(true, "连接成功，模型回复：" + snippet);
        } catch (Exception e) {
            return Map.entry(false, "连接失败：" + e.getMessage());
        }
    }
}
