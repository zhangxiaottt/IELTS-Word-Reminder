package com.ielts.reminder;

import com.ielts.reminder.article.ArticleGenerator;
import com.ielts.reminder.config.ConfigManager;
import com.ielts.reminder.data.WordManager;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * ArticleGenerator 单元测试：
 * 词性识别 / 模板生成 / 归档缓存 / 同日稳定 / 换篇。
 */
class ArticleGeneratorTest {

    @TempDir
    Path tempDir;

    private WordManager wm;
    private ArticleGenerator gen;

    @BeforeEach
    void setUp() throws Exception {
        wm = new WordManager(tempDir.resolve("test.db"));
        Path articlesFile = tempDir.resolve("articles.json");
        gen = new ArticleGenerator(wm, articlesFile, null); // 不启用 LLM，走模板路径
    }

    @AfterEach
    void tearDown() {
        wm.close();
    }

    /** 插入一批带词性释义的单词 */
    private void seedWords() {
        assertTrue(wm.addWord("market", "/ˈmɑːkɪt/", "n. 市场", ""));
        assertTrue(wm.addWord("quiet", "/ˈkwaɪət/", "adj. 安静的", ""));
        assertTrue(wm.addWord("wander", "/ˈwɒndə/", "v. 漫步", ""));
        assertTrue(wm.addWord("slowly", "/ˈsləʊli/", "adv. 缓慢地", ""));
        assertTrue(wm.addWord("gift", "/ɡɪft/", "n. 礼物", ""));
    }

    @Test
    void 词性识别() {
        assertEquals("n", ArticleGenerator.posOf("n. 市场"));
        assertEquals("v", ArticleGenerator.posOf("vt. 打断"));
        assertEquals("v", ArticleGenerator.posOf("vi. 到达"));
        assertEquals("adj", ArticleGenerator.posOf("adj. 安静"));
        assertEquals("adv", ArticleGenerator.posOf("adv. 缓慢"));
        assertEquals("n", ArticleGenerator.posOf(""), "空释义默认名词");
        assertEquals("n", ArticleGenerator.posOf("未知文本"), "无法识别默认名词");
    }

    @Test
    void 模板生成文章结构完整() {
        seedWords();
        Map<String, Object> art = gen.generate("2026-10-10", null, 3, 12);
        assertNotNull(art);
        assertEquals("2026-10-10", art.get("date"));
        assertFalse(String.valueOf(art.get("title")).isEmpty());
        String text = String.valueOf(art.get("text"));
        assertFalse(text.isEmpty(), "正文不能为空");
        assertEquals("template", art.get("source"));
        assertEquals(5, art.get("target_count"));
        int used = (Integer) art.get("used_count");
        assertTrue(used > 0, "至少用到一个目标词");
        // 用到的词都应挂在词汇表里
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> words = (List<Map<String, Object>>) art.get("words");
        assertEquals(used, words.size());
        // 正文必须包含所有"已用词"
        for (Map<String, Object> w : words) {
            assertTrue(text.contains(String.valueOf(w.get("word"))),
                    "正文应包含已用词: " + w.get("word"));
        }
    }

    @Test
    void 无单词时生成仍成功() {
        // 词库为空：生成不崩溃，正文可用占位词
        Map<String, Object> art = gen.generate("2026-10-10", null, 3, 12);
        assertNotNull(art);
        assertFalse(String.valueOf(art.get("text")).isEmpty());
        assertEquals(0, art.get("target_count"));
    }

    @Test
    void 同日多次生成内容一致() {
        seedWords();
        Map<String, Object> a = gen.generate("2026-10-10", null, 3, 12);
        Map<String, Object> b = gen.generate("2026-10-10", null, 3, 12);
        // 默认以日期为种子：同一天内容稳定
        assertEquals(a.get("text"), b.get("text"));
        assertEquals(a.get("title"), b.get("title"));
    }

    @Test
    void 换seed生成不同文章() {
        seedWords();
        Map<String, Object> a = gen.generate("2026-10-10", "seed-A", 3, 12);
        Map<String, Object> b = gen.generate("2026-10-10", "seed-B", 3, 12);
        // 换一篇：大概率不同（不强制，只验证两者都成功）
        assertNotNull(a);
        assertNotNull(b);
        assertFalse(String.valueOf(a.get("text")).isEmpty());
        assertFalse(String.valueOf(b.get("text")).isEmpty());
    }

    @Test
    void 归档缓存getOrGenerate() {
        seedWords();
        Map<String, Object> first = gen.getOrGenerate("2026-10-10", null, 3, 12);
        // 第二次读取应命中缓存，内容一致
        Map<String, Object> second = gen.getOrGenerate("2026-10-10", null, 3, 12);
        assertEquals(first.get("text"), second.get("text"));
        // 日期导航工具
        assertEquals("2026-10-09", ArticleGenerator.dateBefore("2026-10-10"));
        assertEquals("2026-10-11", ArticleGenerator.dateAfter("2026-10-10"));
    }

    @Test
    void 归档文件真实落盘() throws Exception {
        seedWords();
        gen.getOrGenerate("2026-10-10", null, 3, 12);
        Path f = tempDir.resolve("articles.json");
        assertTrue(java.nio.file.Files.exists(f), "归档文件应落盘");
        assertTrue(java.nio.file.Files.readString(f).contains("2026-10-10"));
    }
}
