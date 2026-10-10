package com.ielts.reminder;

import com.ielts.reminder.api.DictAPI;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * DictAPI 单元测试：
 * 空输入返回空 Map；查询不抛异常；结果结构为 phonetic/meaning/example。
 */
class DictAPITest {

    @Test
    void 空输入返回空Map() {
        assertTrue(DictAPI.getInstance().query("").isEmpty());
        assertTrue(DictAPI.getInstance().query(null).isEmpty());
        assertTrue(DictAPI.getInstance().query("   ").isEmpty());
    }

    @Test
    void 真实单词查询不抛异常且结构正确() {
        // 有网环境下查询真实单词；无网/接口变更也不允许抛异常
        Map<String, String> r = assertDoesNotThrow(() -> DictAPI.getInstance().query("apple"));
        assertNotNull(r);
        // 无论查到与否，都必须是三键结构
        assertTrue(r.containsKey("phonetic"));
        assertTrue(r.containsKey("meaning"));
        assertTrue(r.containsKey("example"));
    }

    @Test
    void 单例一致性() {
        assertSame(DictAPI.getInstance(), DictAPI.getInstance());
    }
}
