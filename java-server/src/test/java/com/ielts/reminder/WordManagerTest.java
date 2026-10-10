package com.ielts.reminder;

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
 * WordManager 单元测试：
 * CRUD / 查重 / 熟悉度 ±20 / 复习算法优先级 / 损坏自愈。
 */
class WordManagerTest {

    @TempDir
    Path tempDir;

    private WordManager wm;
    private Path dbFile;

    @BeforeEach
    void setUp() {
        dbFile = tempDir.resolve("test.db");
        wm = new WordManager(dbFile);
    }

    @AfterEach
    void tearDown() {
        wm.close();
    }

    /** 直接改 created_at 模拟"昨天/近5天/历史"录入时间 */
    private void setCreatedAt(long id, String dateTime) {
        wm.updateWordRaw(id, "created_at", dateTime);
    }

    private long add(String word, String meaning) {
        assertTrue(wm.addWord(word, "/f/", meaning, "example"));
        Object id = wm.getWordByWord(word).get("id");
        return ((Number) id).longValue();
    }

    // ------------------------------------------------------------------ //
    // CRUD
    // ------------------------------------------------------------------ //

    @Test
    void 添加与查重() {
        assertTrue(wm.addWord("apple", "/æpl/", "n. 苹果", "An apple a day."));
        assertFalse(wm.addWord("apple", "", "", ""), "重复单词应返回 false");
        assertFalse(wm.addWord("   ", "", "", ""), "空单词应返回 false");
        assertEquals(1, wm.countAll());
        assertNotNull(wm.getWordByWord("apple"));
        assertNull(wm.getWordByWord("banana"));
    }

    @Test
    void 修改与删除() {
        long id = add("cat", "n. 猫");
        assertTrue(wm.updateWord(id, Map.of("meaning", "n. 小猫", "phonetic", "/kæt/")));
        assertEquals("n. 小猫", wm.getWordById(id).get("meaning"));
        assertTrue(wm.deleteWord(id));
        assertNull(wm.getWordById(id));
    }

    @Test
    void 批量删除() {
        long a = add("one", "n. 一");
        long b = add("two", "n. 二");
        long c = add("three", "n. 三");
        assertTrue(wm.deleteWords(List.of(a, b)));
        assertNull(wm.getWordById(a));
        assertNull(wm.getWordById(b));
        assertNotNull(wm.getWordById(c));
    }

    // ------------------------------------------------------------------ //
    // 熟悉度
    // ------------------------------------------------------------------ //

    @Test
    void 认识加20不认识减20并夹取() {
        long id = add("word", "n. 词");
        // 连续 5 次"认识"：20 → 40 → 60 → 80 → 100（验证上限夹取）
        for (int i = 0; i < 5; i++) {
            assertTrue(wm.markFamiliar(id, true));
        }
        assertEquals(100, wm.getWordById(id).get("familiar"), "上限夹取到 100");
        assertEquals(5, wm.getWordById(id).get("review_count"));

        assertTrue(wm.markFamiliar(id, false));
        assertEquals(80, wm.getWordById(id).get("familiar"));
    }

    @Test
    void 不认识下探到0() {
        long id = add("word", "n. 词");
        assertTrue(wm.markFamiliar(id, false));
        assertEquals(0, wm.getWordById(id).get("familiar"));
        assertTrue(wm.markFamiliar(id, false));
        assertEquals(0, wm.getWordById(id).get("familiar"), "下限夹取到 0");
    }

    @Test
    void 标记不存在的单词返回false() {
        assertFalse(wm.markFamiliar(99999, true));
    }

    // ------------------------------------------------------------------ //
    // 复习列表优先级：昨日新词 → 近5天 → 历史随机
    // ------------------------------------------------------------------ //

    @Test
    void 复习列表按优先级排序() {
        // 昨天录入（生词 familiar=0 优先）
        long yesterdayId = add("yesterday_word", "n. 昨天");
        setCreatedAt(yesterdayId, java.time.LocalDate.now().minusDays(1) + " 09:00:00");
        // 近5天（今天）
        long todayId = add("today_word", "n. 今天");
        setCreatedAt(todayId, java.time.LocalDate.now() + " 09:00:00");
        // 历史（6 天前）
        long oldId = add("old_word", "n. 老词");
        setCreatedAt(oldId, java.time.LocalDate.now().minusDays(6) + " 09:00:00");

        List<Map<String, Object>> list = wm.getReviewWordList();
        // 昨日新词必须排在最前
        assertEquals(3, list.size());
        assertEquals("yesterday_word", list.get(0).get("word"));
        // 近5天第二
        assertEquals("today_word", list.get(1).get("word"));
        // 历史词最后
        assertEquals("old_word", list.get(2).get("word"));
    }

    @Test
    void 生词优先于熟词() {
        long known = add("known", "n. 熟词");
        setCreatedAt(known, java.time.LocalDate.now().minusDays(1) + " 09:00:00");
        wm.markFamiliar(known, true); // familiar=20

        long neww = add("neww", "n. 生词");
        setCreatedAt(neww, java.time.LocalDate.now().minusDays(1) + " 10:00:00");

        List<Map<String, Object>> list = wm.getReviewWordList();
        assertEquals("neww", list.get(0).get("word"), "生词（familiar 低）应排前");
    }

    // ------------------------------------------------------------------ //
    // 查询与统计
    // ------------------------------------------------------------------ //

    @Test
    void 关键词搜索与时间筛选() {
        add("apple", "n. 苹果");
        add("application", "n. 应用");
        add("banana", "n. 香蕉");

        assertEquals(2, wm.getAllWords("app", null, null).size());
        assertEquals(3, wm.getAllWords(null, null, null).size());

        String today = java.time.LocalDate.now().toString();
        assertEquals(3, wm.getAllWords(null, today, today).size());
        assertEquals(0, wm.getAllWords(null, "2000-01-01", "2000-01-02").size());
    }

    @Test
    void 最近单词与随机取词() {
        add("alpha", "n. 阿尔法");
        add("beta", "n. 贝塔");
        add("gamma", "n. 伽马");
        assertEquals(3, wm.getRecentWords(3, 12).size());
        List<Map<String, Object>> rand = wm.getRandomWords(2, 100);
        assertEquals(2, rand.size());
    }

    // ------------------------------------------------------------------ //
    // 损坏自愈
    // ------------------------------------------------------------------ //

    @Test
    void 数据库损坏自动备份并重建() throws Exception {
        wm.addWord("keep", "n. 保留", "词", "");
        wm.close();

        // 人为破坏数据库文件
        java.nio.file.Files.writeString(dbFile, "这不是一个合法的数据库文件",
                java.nio.charset.StandardCharsets.UTF_8);

        // 重新初始化：不应崩溃，应自动备份 + 重建空库
        WordManager wm2 = new WordManager(dbFile);
        assertEquals(0, wm2.countAll(), "重建后为空库");
        assertTrue(java.nio.file.Files.exists(
                dbFile.resolveSibling("test.db.bak")), "旧库应备份为 .bak");
        wm2.close();
    }
}
