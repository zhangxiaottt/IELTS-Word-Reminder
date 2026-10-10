package com.ielts.reminder.config;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * 项目路径定位工具。
 *
 * 所有路径一律使用「相对项目根目录」解析，保证打包/换目录后仍可正常使用。
 * 定位规则：从当前工作目录向上逐级查找包含 config/ 目录的目录作为项目根；
 * 找不到时回退到当前工作目录本身。
 */
public final class ProjectPaths {

    /** 项目根目录（懒加载缓存） */
    private static Path root;

    private ProjectPaths() {
    }

    /** 定位并返回项目根目录 */
    public static synchronized Path root() {
        if (root == null) {
            root = findRoot();
        }
        return root;
    }

    /** 从当前工作目录向上查找项目根 */
    private static Path findRoot() {
        Path cur = Paths.get("").toAbsolutePath().normalize();
        // 最多向上找 6 层，避免无限上溯
        for (int i = 0; i < 6; i++) {
            if (Files.isDirectory(cur.resolve("config"))) {
                return cur;
            }
            Path parent = cur.getParent();
            if (parent == null) {
                break;
            }
            cur = parent;
        }
        return Paths.get("").toAbsolutePath().normalize();
    }

    /** config/config.json */
    public static Path configPath() {
        return root().resolve("config").resolve("config.json");
    }

    /** data/word_lib.db */
    public static Path dbPath() {
        return root().resolve("data").resolve("word_lib.db");
    }

    /** data/articles.json */
    public static Path articlesPath() {
        return root().resolve("data").resolve("articles.json");
    }

    /** assets/ */
    public static Path assetsPath() {
        return root().resolve("assets");
    }
}
