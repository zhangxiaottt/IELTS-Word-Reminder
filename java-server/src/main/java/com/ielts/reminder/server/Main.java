package com.ielts.reminder.server;

import com.ielts.reminder.api.DictAPI;
import com.ielts.reminder.api.LLMClient;
import com.ielts.reminder.article.ArticleGenerator;
import com.ielts.reminder.config.ConfigManager;
import com.ielts.reminder.data.WordManager;

/**
 * Java 服务层入口：组装各模块并启动本地 REST 服务。
 *
 * 启动方式（由 Python 主程序自动拉起，也可手动运行）：
 *     java -cp "out;lib/*" com.ielts.reminder.server.Main [port]
 */
public class Main {

    public static void main(String[] args) {
        int port = args.length > 0 ? Integer.parseInt(args[0]) : LocalServer.DEFAULT_PORT;

        // 组装服务层各模块
        ConfigManager config = new ConfigManager();
        WordManager wordManager = new WordManager();
        DictAPI dictApi = DictAPI.getInstance();
        LLMClient llmClient = new LLMClient(config);
        ArticleGenerator articleGenerator = new ArticleGenerator(wordManager, llmClient);

        LocalServer server = new LocalServer(config, wordManager, dictApi,
                llmClient, articleGenerator);
        try {
            server.start();
        } catch (Exception e) {
            System.err.println("[Main] 启动失败: " + e.getMessage());
            System.exit(1);
        }

        // 优雅关闭：Ctrl+C 或 JVM 退出时释放资源
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            server.stop();
            wordManager.close();
        }));
    }
}
