package com.ielts.reminder.config;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 配置管理器：封装 config.json 的读写，提供统一 get/set 方法。
 *
 * 设计要点（与 Python 版 ConfigManager 对齐）：
 * - 点号路径访问：get("panel.opacity") / set("review.interval", 12)
 * - 默认配置深合并：文件里缺的字段用默认值补全，多出的字段保留
 * - 配置文件损坏或不存在时：自动备份旧文件为 .bak，再生成默认配置
 */
public class ConfigManager {

    /** 默认配置（与 Python 版默认值保持一致） */
    private static final Map<String, Object> DEFAULTS = buildDefaults();

    private final Path configPath;
    private final Map<String, Object> data;
    private final Gson gson = new GsonBuilder().setPrettyPrinting().create();

    public ConfigManager() {
        this(ProjectPaths.configPath());
    }

    public ConfigManager(Path configPath) {
        this.configPath = configPath;
        this.data = load();
    }

    /** 构造默认配置树 */
    private static Map<String, Object> buildDefaults() {
        Map<String, Object> panel = new LinkedHashMap<>();
        panel.put("x", 100);
        panel.put("y", 100);
        panel.put("width", 320);
        panel.put("height", 120);
        panel.put("opacity", 0.85);
        panel.put("pet_enabled", true);
        panel.put("house", true);
        panel.put("background", "");

        Map<String, Object> review = new LinkedHashMap<>();
        review.put("interval", 10);
        review.put("auto_start", true);

        Map<String, Object> shortcut = new LinkedHashMap<>();
        shortcut.put("input", "Ctrl+Alt+W");
        shortcut.put("toggle", "Ctrl+Alt+S");

        Map<String, Object> llm = new LinkedHashMap<>();
        llm.put("enabled", false);
        llm.put("base_url", "https://api.deepseek.com");
        llm.put("api_key", "");
        llm.put("model", "deepseek-chat");

        Map<String, Object> defaults = new LinkedHashMap<>();
        defaults.put("panel", panel);
        defaults.put("review", review);
        defaults.put("shortcut", shortcut);
        defaults.put("auto_launch", false);
        defaults.put("llm", llm);
        return defaults;
    }

    /** 读取配置文件；损坏/不存在时备份并回退默认配置 */
    @SuppressWarnings("unchecked")
    private Map<String, Object> load() {
        if (!Files.exists(configPath)) {
            // 文件不存在：直接用默认配置并落盘
            Map<String, Object> fresh = deepMerge(DEFAULTS, new LinkedHashMap<>());
            writeJson(fresh);
            return fresh;
        }
        try {
            String text = Files.readString(configPath, StandardCharsets.UTF_8);
            JsonElement el = JsonParser.parseString(text);
            if (!el.isJsonObject()) {
                throw new IOException("config.json 根节点不是 JSON 对象");
            }
            Map<String, Object> fileMap = gson.fromJson(el, LinkedHashMap.class);
            return deepMerge(DEFAULTS, fileMap);
        } catch (Exception e) {
            // 解析失败：备份损坏文件，回退默认配置
            backupBrokenFile();
            Map<String, Object> fresh = deepMerge(DEFAULTS, new LinkedHashMap<>());
            writeJson(fresh);
            return fresh;
        }
    }

    /** 深度合并：base 为默认值，override 优先；均为 Map 时递归合并。
     *  注意：base 必须先深拷贝，否则 set() 会污染静态默认配置树。 */
    private static Map<String, Object> deepMerge(Map<String, Object> base, Map<String, Object> override) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<String, Object> e : base.entrySet()) {
            result.put(e.getKey(), copyDeep(e.getValue()));
        }
        for (Map.Entry<String, Object> entry : override.entrySet()) {
            Object v = entry.getValue();
            Object old = result.get(entry.getKey());
            if (v instanceof Map && old instanceof Map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> oldMap = (Map<String, Object>) old;
                @SuppressWarnings("unchecked")
                Map<String, Object> vMap = (Map<String, Object>) v;
                result.put(entry.getKey(), deepMerge(oldMap, vMap));
            } else {
                result.put(entry.getKey(), copyDeep(v));
            }
        }
        return result;
    }

    /** 深拷贝任意值（Map/List 递归复制，避免共享引用被外部修改） */
    @SuppressWarnings("unchecked")
    private static Object copyDeep(Object v) {
        if (v instanceof Map) {
            Map<String, Object> m = new LinkedHashMap<>();
            for (Map.Entry<String, Object> e : ((Map<String, Object>) v).entrySet()) {
                m.put(e.getKey(), copyDeep(e.getValue()));
            }
            return m;
        }
        if (v instanceof List) {
            List<Object> l = new java.util.ArrayList<>();
            for (Object o : (List<Object>) v) {
                l.add(copyDeep(o));
            }
            return l;
        }
        return v;
    }

    /** 备份损坏的配置文件为 .bak */
    private void backupBrokenFile() {
        try {
            if (Files.exists(configPath)) {
                Files.copy(configPath, configPath.resolveSibling("config.json.bak"),
                        java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException ignored) {
            // 备份失败不影响程序继续运行
        }
    }

    /** 将配置树写回 config.json */
    public synchronized boolean save() {
        return writeJson(data);
    }

    private synchronized boolean writeJson(Map<String, Object> tree) {
        try {
            Files.createDirectories(configPath.getParent());
            String json = gson.toJson(tree);
            Files.writeString(configPath, json, StandardCharsets.UTF_8);
            return true;
        } catch (IOException e) {
            return false;
        }
    }

    /** 按点号路径取值：get("panel.opacity", 0.85) */
    @SuppressWarnings("unchecked")
    public Object get(String key, Object defaultValue) {
        Object cur = data;
        for (String part : key.split("\\.")) {
            if (!(cur instanceof Map)) {
                return defaultValue;
            }
            cur = ((Map<String, Object>) cur).get(part);
            if (cur == null) {
                return defaultValue;
            }
        }
        return normalize(cur, defaultValue);
    }

    /** 数值/布尔类型归一化：JSON 数字默认解析为 Double，按调用方期望类型转换 */
    private static Object normalize(Object value, Object defaultValue) {
        if (defaultValue instanceof Integer && value instanceof Number) {
            return ((Number) value).intValue();
        }
        if (defaultValue instanceof Double && value instanceof Number) {
            return ((Number) value).doubleValue();
        }
        if (defaultValue instanceof Boolean && value instanceof Boolean) {
            return value;
        }
        return value;
    }

    /** 便捷方法：int 读取 */
    public int getInt(String key, int defaultValue) {
        Object v = get(key, defaultValue);
        return v instanceof Number ? ((Number) v).intValue() : defaultValue;
    }

    /** 便捷方法：double 读取 */
    public double getDouble(String key, double defaultValue) {
        Object v = get(key, defaultValue);
        return v instanceof Number ? ((Number) v).doubleValue() : defaultValue;
    }

    /** 便捷方法：boolean 读取 */
    public boolean getBool(String key, boolean defaultValue) {
        Object v = get(key, defaultValue);
        return v instanceof Boolean ? (Boolean) v : defaultValue;
    }

    /** 便捷方法：String 读取 */
    public String getString(String key, String defaultValue) {
        Object v = get(key, defaultValue);
        return v == null ? defaultValue : String.valueOf(v);
    }

    /** 按点号路径写值：set("review.interval", 12)，路径不存在则自动创建 */
    @SuppressWarnings("unchecked")
    public void set(String key, Object value) {
        String[] parts = key.split("\\.");
        Map<String, Object> cur = data;
        for (int i = 0; i < parts.length - 1; i++) {
            Object next = cur.get(parts[i]);
            if (!(next instanceof Map)) {
                Map<String, Object> fresh = new LinkedHashMap<>();
                cur.put(parts[i], fresh);
                cur = fresh;
            } else {
                cur = (Map<String, Object>) next;
            }
        }
        cur.put(parts[parts.length - 1], value);
    }

    /** 返回整个配置树（深拷贝，避免外部篡改内部状态） */
    public Map<String, Object> getData() {
        return deepMerge(data, new LinkedHashMap<>());
    }
}
