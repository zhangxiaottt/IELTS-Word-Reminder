package com.ielts.reminder.api;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * 有道词典 API 封装（单例）。
 *
 * 查询策略（与 Python 版对齐）：
 * 1. 优先调用有道 jsonapi 接口（音标/释义/双语例句，信息最全）
 * 2. 失败时回退 suggest 联想接口（音标/释义）
 * 3. 仍失败则返回空 Map
 *
 * 规则：请求超时 3 秒；查询失败/单词不存在均返回空 Map，绝不抛出异常。
 */
public class DictAPI {

    /** 单例实例 */
    private static final DictAPI INSTANCE = new DictAPI();

    private static final String JSONAPI_URL = "https://dict.youdao.com/jsonapi";
    private static final String SUGGEST_URL = "https://dict.youdao.com/suggest";
    private static final int TIMEOUT_SECONDS = 3;

    /** 去除释义前缀序号：如 "1. 融化" -> "融化" */
    private static final Pattern SEQ_PREFIX = Pattern.compile("^\\d+\\.\\s*");

    /** 复用同一个 HttpClient，减少握手开销 */
    private final HttpClient client;

    private DictAPI() {
        client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(TIMEOUT_SECONDS))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
    }

    /** 获取单例 */
    public static DictAPI getInstance() {
        return INSTANCE;
    }

    // ------------------------------------------------------------------ //
    // 对外查询入口
    // ------------------------------------------------------------------ //

    /** 查询英文单词，返回 {"phonetic","meaning","example"}；失败返回空 Map */
    public Map<String, String> query(String word) {
        if (word == null) {
            return Map.of();
        }
        String w = word.trim().toLowerCase();
        if (w.isEmpty()) {
            return Map.of();
        }

        // 1. 优先 jsonapi（信息最全，含例句）
        Map<String, String> result = queryJsonapi(w);
        if (!result.isEmpty()) {
            return result;
        }
        // 2. 回退 suggest 联想接口
        result = querySuggest(w);
        if (!result.isEmpty()) {
            return result;
        }
        // 3. 全部失败
        return Map.of();
    }

    // ------------------------------------------------------------------ //
    // jsonapi 接口（音标 / 释义 / 双语例句）
    // ------------------------------------------------------------------ //

    private Map<String, String> queryJsonapi(String word) {
        try {
            String body = httpGet(JSONAPI_URL + "?q=" + encode(word));
            if (body == null) {
                return Map.of();
            }
            JsonObject data = JsonParser.parseString(body).getAsJsonObject();
            String phonetic = extractPhonetic(data);
            String meaning = extractMeaning(data);
            String example = extractExample(data);
            if (phonetic.isEmpty() && meaning.isEmpty() && example.isEmpty()) {
                return Map.of();
            }
            Map<String, String> r = new LinkedHashMap<>();
            r.put("phonetic", phonetic);
            r.put("meaning", meaning);
            r.put("example", example);
            return r;
        } catch (Exception e) {
            return Map.of();
        }
    }

    /** 提取音标（优先英式 ukphone，其次美式 usphone；回退短语区音标） */
    private static String extractPhonetic(JsonObject data) {
        try {
            JsonArray words = data.getAsJsonObject("ec").getAsJsonArray("word");
            if (words != null && words.size() > 0) {
                JsonObject w = words.get(0).getAsJsonObject();
                String uk = optString(w, "ukphone");
                String us = optString(w, "usphone");
                if (!uk.isEmpty()) {
                    return uk;
                }
                if (!us.isEmpty()) {
                    return us;
                }
            }
        } catch (Exception ignored) {
        }
        try {
            JsonArray phrs = data.getAsJsonObject("phrs").getAsJsonArray("phrs");
            if (phrs != null && phrs.size() > 0) {
                return optString(phrs.get(0).getAsJsonObject(), "p");
            }
        } catch (Exception ignored) {
        }
        return "";
    }

    /** 提取中文释义（拼接多个词性释义，兼容字符串/字典两种 i 结构） */
    private static String extractMeaning(JsonObject data) {
        try {
            JsonArray trs = data.getAsJsonObject("ec")
                    .getAsJsonArray("word").get(0).getAsJsonObject()
                    .getAsJsonArray("trs");
            if (trs == null) {
                return "";
            }
            StringBuilder sb = new StringBuilder();
            for (JsonElement trEl : trs) {
                JsonArray trArr = trEl.getAsJsonObject().getAsJsonArray("tr");
                if (trArr == null || trArr.size() == 0) {
                    continue;
                }
                JsonArray iArr = trArr.get(0).getAsJsonObject()
                        .getAsJsonObject("l").getAsJsonArray("i");
                if (iArr == null || iArr.size() == 0) {
                    continue;
                }
                JsonElement item = iArr.get(0);
                String text;
                if (item.isJsonObject()) {
                    text = optString(item.getAsJsonObject(), "t");
                } else {
                    text = item.getAsString();
                }
                text = SEQ_PREFIX.matcher(text.trim()).replaceFirst("");
                if (!text.isEmpty()) {
                    if (sb.length() > 0) {
                        sb.append("；");
                    }
                    sb.append(text);
                }
            }
            return sb.toString();
        } catch (Exception e) {
            return "";
        }
    }

    /** 提取首条双语例句（英文 + 中文） */
    private static String extractExample(JsonObject data) {
        try {
            JsonArray pairs = data.getAsJsonObject("blng_sents_part")
                    .getAsJsonArray("sentence-pair");
            if (pairs == null || pairs.size() == 0) {
                return "";
            }
            JsonObject first = pairs.get(0).getAsJsonObject();
            String en = optString(first, "sentence");
            String zh = optString(first, "sentence-translation");
            if (en.isEmpty()) {
                return "";
            }
            if (!zh.isEmpty()) {
                return en + "  " + zh;
            }
            return en;
        } catch (Exception e) {
            return "";
        }
    }

    // ------------------------------------------------------------------ //
    // suggest 联想接口（音标 + 释义）
    // ------------------------------------------------------------------ //

    private Map<String, String> querySuggest(String word) {
        try {
            String url = SUGGEST_URL + "?num=5&ver=3.0&doctype=json&cache=false"
                    + "&le=en&q=" + encode(word);
            String body = httpGet(url);
            if (body == null) {
                return Map.of();
            }
            JsonObject data = JsonParser.parseString(body).getAsJsonObject();
            JsonArray entries = data.getAsJsonObject("data").getAsJsonArray("entries");
            if (entries == null || entries.size() == 0) {
                return Map.of();
            }
            JsonObject entry = entries.get(0).getAsJsonObject();
            String phonetic = "";
            try {
                JsonObject pronounce = entry.getAsJsonObject("pronounce");
                phonetic = optString(pronounce, "uk");
                if (phonetic.isEmpty()) {
                    phonetic = optString(pronounce, "ame");
                }
            } catch (Exception ignored) {
            }
            String meaning = optString(entry, "explain");
            if (meaning.isEmpty()) {
                JsonArray trans = entry.getAsJsonArray("translation");
                if (trans != null && trans.size() > 0) {
                    meaning = trans.get(0).getAsString().trim();
                }
            }
            if (meaning.isEmpty() && phonetic.isEmpty()) {
                return Map.of();
            }
            Map<String, String> r = new LinkedHashMap<>();
            r.put("phonetic", phonetic);
            r.put("meaning", meaning);
            r.put("example", "");
            return r;
        } catch (Exception e) {
            return Map.of();
        }
    }

    // ------------------------------------------------------------------ //
    // 工具
    // ------------------------------------------------------------------ //

    /** GET 请求，返回响应体；任何异常返回 null */
    private String httpGet(String url) {
        try {
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(TIMEOUT_SECONDS))
                    .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            + "AppleWebKit/537.36 (KHTML, like Gecko) "
                            + "Chrome/120.0.0.0 Safari/537.36")
                    .header("Referer", "https://www.youdao.com/")
                    .GET()
                    .build();
            HttpResponse<String> resp = client.send(req,
                    HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() != 200) {
                return null;
            }
            return resp.body();
        } catch (Exception e) {
            return null;
        }
    }

    private static String optString(JsonObject obj, String key) {
        JsonElement el = obj.get(key);
        if (el == null || el.isJsonNull()) {
            return "";
        }
        return el.getAsString().trim();
    }

    /** URL 编码（用标准库，避免中文/空格问题） */
    private static String encode(String s) {
        return java.net.URLEncoder.encode(s, java.nio.charset.StandardCharsets.UTF_8);
    }
}
