package com.ielts.reminder;

import com.ielts.reminder.config.ConfigManager;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

/**
 * ConfigManager 单元测试：
 * 默认值 / 点号读写 / 保存重载 / 损坏文件自愈备份。
 */
class ConfigManagerTest {

    @TempDir
    Path tempDir;

    private Path cfgFile() {
        return tempDir.resolve("config.json");
    }

    @Test
    void 文件不存在时使用默认配置() throws Exception {
        ConfigManager cm = new ConfigManager(cfgFile());
        assertEquals(10, cm.getInt("review.interval", -1));
        assertEquals(0.85, cm.getDouble("panel.opacity", -1), 0.0001);
        assertEquals("Ctrl+Alt+W", cm.getString("shortcut.input", ""));
        assertFalse(cm.getBool("auto_launch", true));
        // 文件应被自动创建
        assertTrue(Files.exists(cfgFile()));
    }

    @Test
    void 点号读写与保存重载() throws Exception {
        ConfigManager cm = new ConfigManager(cfgFile());
        cm.set("review.interval", 15);
        cm.set("panel.opacity", 0.7);
        cm.set("llm.model", "deepseek-chat");
        assertTrue(cm.save());

        // 用新实例重读，验证落盘
        ConfigManager cm2 = new ConfigManager(cfgFile());
        assertEquals(15, cm2.getInt("review.interval", -1));
        assertEquals(0.7, cm2.getDouble("panel.opacity", -1), 0.0001);
        assertEquals("deepseek-chat", cm2.getString("llm.model", ""));
    }

    @Test
    void 不存在的键返回默认值() {
        ConfigManager cm = new ConfigManager(cfgFile());
        assertEquals(42, cm.getInt("no.such.key", 42));
        assertEquals("fallback", cm.getString("missing", "fallback"));
        assertTrue(cm.getBool("missing.bool", true));
    }

    @Test
    void 损坏配置文件自动备份并回退默认() throws Exception {
        // 写入非法 JSON
        Files.writeString(cfgFile(), "{ 这不是合法JSON ", StandardCharsets.UTF_8);

        ConfigManager cm = new ConfigManager(cfgFile());
        // 配置回退默认
        assertEquals(10, cm.getInt("review.interval", -1));
        // 损坏文件被备份为 .bak
        assertTrue(Files.exists(cfgFile().resolveSibling("config.json.bak")));
        // 主文件被重建为合法 JSON
        assertTrue(Files.readString(cfgFile(), StandardCharsets.UTF_8).contains("review"));
    }

    @Test
    void 文件中的自定义值覆盖默认值() throws Exception {
        Files.writeString(cfgFile(),
                "{\"panel\":{\"opacity\":0.5},\"llm\":{\"model\":\"gpt-test\"}}",
                StandardCharsets.UTF_8);
        ConfigManager cm = new ConfigManager(cfgFile());
        // 覆盖生效
        assertEquals(0.5, cm.getDouble("panel.opacity", -1), 0.0001);
        assertEquals("gpt-test", cm.getString("llm.model", ""));
        // 未覆盖的默认保留
        assertEquals(10, cm.getInt("review.interval", -1));
    }
}
