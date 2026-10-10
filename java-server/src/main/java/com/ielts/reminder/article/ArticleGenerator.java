package com.ielts.reminder.article;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.ielts.reminder.api.LLMClient;
import com.ielts.reminder.config.ProjectPaths;
import com.ielts.reminder.data.WordManager;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 每日复习文章生成器。
 *
 * 把最近几天学过的单词编进一篇连贯的英文短文：
 * 1. 从词库取最近 N 天录入的单词（默认 3 天，最多 12 个）
 * 2. 按词性（名词/动词/形容词/副词）匹配到「故事模板」的槽位
 * 3. 每天的文章按日期归档到 data/articles.json，可换一篇、可回看历史
 *
 * AI 双路：配置并启用大模型时优先用 AI 写文章，调用失败自动回落本地模板。
 */
public class ArticleGenerator {

    /** 占位词：某词性没有可用目标词时用于补位，保证句子完整通顺 */
    private static final Map<String, String> FILLER = new LinkedHashMap<>();
    static {
        FILLER.put("n", "book");
        FILLER.put("v", "look");
        FILLER.put("adj", "quiet");
        FILLER.put("adv", "slowly");
        FILLER.put("any", "thing");
    }

    /** 词性识别：有道中文释义一般带 "n. / v. / adj." 等前缀 */
    private static final Pattern POS_RE = Pattern.compile(
            "^\\s*(n|v|vt|vi|adj|adv|prep|conj|pron|num|art|int)\\.?\\s*",
            Pattern.CASE_INSENSITIVE);

    /** 归一到三类核心词性（未识别默认名词） */
    private static final Map<String, String> POS_MAP = new LinkedHashMap<>();
    static {
        POS_MAP.put("n", "n");
        POS_MAP.put("v", "v");
        POS_MAP.put("vt", "v");
        POS_MAP.put("vi", "v");
        POS_MAP.put("adj", "adj");
        POS_MAP.put("adv", "adv");
    }

    // ------------------------------------------------------------------ //
    // 故事模板池（与 Python 版保持一致）
    // ------------------------------------------------------------------ //

    /** 模板主题：标题 + 片段列表（"{}" 为槽位，None 为固定叙述句） */
    public static final List<Map<String, Object>> THEMES = buildThemes();

    private static List<Map<String, Object>> buildThemes() {
        List<Map<String, Object>> themes = new ArrayList<>();
        themes.add(theme("The Morning Market", new String[][]{
            {"Early on Saturday, Anna went to the morning market. ", null},
            {"The crowd made the old street feel alive; she noticed every {} around her.", "n"},
            {"She walked slowly and looked at everything with fresh eyes. ", null},
            {"The whole morning felt bright and {}.", "adj"},
            {"A young man sold fruit in a cheerful voice. ", null},
            {"Anna stopped to {} for a while before moving on.", "v"},
            {"When the sun rose higher, she picked a small gift. ", null},
            {"She chose a little {} and paid for it with a smile.", "n"},
            {"Walking home, she felt light and happy. ", null},
            {"It had been a truly {} morning.", "adj"},
        }));
        themes.add(theme("A Rainy Day", new String[][]{
            {"The rain began at noon. ", null},
            {"Drops of water covered every {} on the street.", "n"},
            {"Mike stayed inside with a cup of hot tea. ", null},
            {"The room felt quiet and {}.", "adj"},
            {"He watched the window for a long time. ", null},
            {"Soon he decided to {} his homework.", "v"},
            {"Outside, the street was empty and grey. ", null},
            {"It was a {} afternoon.", "adj"},
            {"When evening came, the rain finally stopped. ", null},
            {"He put his {} on the table and smiled.", "n"},
        }));
        themes.add(theme("The Library Afternoon", new String[][]{
            {"Lily spent her afternoon in the school library. ", null},
            {"She took out a {} from her bag and began to read.", "n"},
            {"The pages turned slowly in the quiet room. ", null},
            {"Everything felt {} and calm.", "adj"},
            {"Sometimes she stopped reading for a moment. ", null},
            {"She liked to {} before turning the page.", "v"},
            {"After an hour, she carried her books home. ", null},
            {"A small {} was under her arm.", "n"},
            {"Lily smiled as she walked. ", null},
            {"It was exactly the {} ending she needed.", "adj"},
        }));
        themes.add(theme("The Trip to the City", new String[][]{
            {"Tom took the early bus to the city. ", null},
            {"The street was full of noise and {}.", "n"},
            {"He had a map in one hand and a ticket in the other. ", null},
            {"The tall buildings looked {}.", "adj"},
            {"For lunch he found a small restaurant. ", null},
            {"He ordered a bowl of noodles and began to {}.", "v"},
            {"In the afternoon, he walked along the river. ", null},
            {"He bought a {} from a small shop by the water.", "n"},
            {"On the way home, Tom thought about the day. ", null},
            {"It had been simple but {}.", "adj"},
        }));
        themes.add(theme("Cooking Dinner", new String[][]{
            {"Mia decided to cook dinner for her family. ", null},
            {"She opened the fridge and took out a {}.", "n"},
            {"The kitchen smelled warm and sweet. ", null},
            {"Cooking always made her feel {}.", "adj"},
            {"She followed the recipe step by step. ", null},
            {"Carefully, she began to {} in the quiet kitchen.", "v"},
            {"Soon the whole house was full of a good smell. ", null},
            {"She put the {} on the table with pride.", "n"},
            {"At dinner, everyone smiled. ", null},
            {"Her parents said the meal was {}.", "adj"},
        }));
        themes.add(theme("The Evening Walk", new String[][]{
            {"After dinner, Dad and I went for a walk. ", null},
            {"I picked up a tiny {} from the path and put it in my pocket.", "n"},
            {"The air was cool and fresh. ", null},
            {"The evening sky looked {}.", "adj"},
            {"We talked about small things and laughed. ", null},
            {"Sometimes we stopped to {} together.", "v"},
            {"On the way back, the moon came out. ", null},
            {"Dad found a {} and showed it to me.", "n"},
            {"I smiled all the way home. ", null},
            {"It was a simple, {} evening.", "adj"},
        }));
        themes.add(theme("The School Trip", new String[][]{
            {"The whole class went on a school trip. ", null},
            {"Everyone carried a {} in their bag.", "n"},
            {"The bus left early in the morning. ", null},
            {"The weather was warm and {}.", "adj"},
            {"At the museum, the guide spoke clearly. ", null},
            {"The students listened and began to {}.", "v"},
            {"At lunch, they sat together under a tree. ", null},
            {"Someone shared a {} with the group.", "n"},
            {"By the end of the day, everyone was tired but happy. ", null},
            {"It was a {} day they would remember.", "adj"},
        }));
        themes.add(theme("The Busy Weekend", new String[][]{
            {"This weekend was busier than usual. ", null},
            {"On Saturday morning, Tom found a {} in the drawer.", "n"},
            {"He worked until noon without stopping. ", null},
            {"The room finally looked {}.", "adj"},
            {"In the afternoon, his friend called. ", null},
            {"They decided to {} together in the park.", "v"},
            {"They talked and laughed for hours. ", null},
            {"Later, they bought a {} from a street stand.", "n"},
            {"By night, Tom felt tired but pleased. ", null},
            {"It had been a long, {} day.", "adj"},
        }));
        return themes;
    }

    /** 构造一个主题（片段数组：[句子, 词性或 null]） */
    private static Map<String, Object> theme(String title, String[][] parts) {
        List<Object[]> list = new ArrayList<>();
        for (String[] p : parts) {
            list.add(new Object[]{p[0], p[1]});
        }
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("title", title);
        m.put("parts", list);
        return m;
    }

    /** 从中文释义提取词性（n/v/adj/adv/any），失败默认名词 */
    public static String posOf(String meaning) {
        if (meaning == null || meaning.isEmpty()) {
            return "n";
        }
        Matcher m = POS_RE.matcher(meaning.trim());
        if (m.find()) {
            String key = m.group(1).toLowerCase();
            return POS_MAP.getOrDefault(key, "n");
        }
        return "n";
    }

    // ------------------------------------------------------------------ //
    // 归档
    // ------------------------------------------------------------------ //

    private final WordManager wm;
    private final Path dataFile;
    private final LLMClient llm;
    private final Gson gson = new GsonBuilder().setPrettyPrinting().create();
    private Map<String, Object> store;

    public ArticleGenerator(WordManager wm, LLMClient llm) {
        this(wm, ProjectPaths.articlesPath(), llm);
    }

    public ArticleGenerator(WordManager wm, Path dataFile, LLMClient llm) {
        this.wm = wm;
        this.dataFile = dataFile;
        this.llm = llm;
        this.store = loadStore();
    }

    /** 读取本地文章归档；损坏/缺失返回空 Map */
    @SuppressWarnings("unchecked")
    private Map<String, Object> loadStore() {
        try {
            if (!Files.exists(dataFile)) {
                return new LinkedHashMap<>();
            }
            String text = Files.readString(dataFile, StandardCharsets.UTF_8);
            JsonElement el = JsonParser.parseString(text);
            if (!el.isJsonObject()) {
                return new LinkedHashMap<>();
            }
            return gson.fromJson(el, LinkedHashMap.class);
        } catch (Exception e) {
            return new LinkedHashMap<>();
        }
    }

    /** 写回本地归档（失败仅跳过，不影响主流程） */
    private void saveStore() {
        try {
            Files.createDirectories(dataFile.getParent());
            Files.writeString(dataFile, gson.toJson(store), StandardCharsets.UTF_8);
        } catch (IOException ignored) {
        }
    }

    /** 保存某一天的文章到归档 */
    public void save(String dateStr, Map<String, Object> article) {
        store.put(dateStr, article);
        saveStore();
    }

    /** 读取某一天的文章，不存在返回 null */
    public Map<String, Object> load(String dateStr) {
        Object v = store.get(dateStr);
        if (v instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> m = (Map<String, Object>) v;
            return m;
        }
        return null;
    }

    // ------------------------------------------------------------------ //
    // 取词
    // ------------------------------------------------------------------ //

    /** 最近 N 天录入的单词（用于编入文章） */
    public List<Map<String, Object>> getTargetWords(int days, int limit) {
        return wm.getRecentWords(days, limit);
    }

    // ------------------------------------------------------------------ //
    // 生成
    // ------------------------------------------------------------------ //

    /**
     * 为指定日期生成一篇复习文章。
     * dateStr 默认今天；seed 固定可复现（默认以日期为种子保证当天稳定）。
     */
    public Map<String, Object> generate(String dateStr, String seed,
                                        int days, int limit) {
        if (dateStr == null) {
            dateStr = LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE);
        }
        List<Map<String, Object>> words = getTargetWords(days, limit);

        // AI 路径：配置了 LLM 且调用成功则用 AI 写文章；失败自动回落模板
        if (llm != null && llm.enabled()) {
            Map<String, Object> art = generateWithLlm(dateStr, words);
            if (art != null) {
                return art;
            }
        }

        // 模板兜底路径（离线 / 未配置 key / AI 失败时使用）
        Random rng = new Random(seed != null ? seed.hashCode() : dateStr.hashCode());
        @SuppressWarnings("unchecked")
        Map<String, Object> theme = (Map<String, Object>)
                THEMES.get(rng.nextInt(THEMES.size()));

        // 按词性分组并打乱，保证每次选的词更随机
        Map<String, List<Map<String, Object>>> buckets = new LinkedHashMap<>();
        buckets.put("n", new ArrayList<>());
        buckets.put("v", new ArrayList<>());
        buckets.put("adj", new ArrayList<>());
        buckets.put("adv", new ArrayList<>());
        buckets.put("any", new ArrayList<>());
        for (Map<String, Object> row : words) {
            String pos = posOf(String.valueOf(row.getOrDefault("meaning", "")));
            buckets.get(pos).add(row);
        }
        for (List<Map<String, Object>> list : buckets.values()) {
            java.util.Collections.shuffle(list, rng);
        }

        Set<Long> usedIds = new LinkedHashSet<>();
        List<Map<String, Object>> used = new ArrayList<>();
        List<String> text = new ArrayList<>();
        @SuppressWarnings("unchecked")
        List<Object[]> parts = (List<Object[]>) theme.get("parts");
        for (Object[] part : parts) {
            String sentence = (String) part[0];
            if (sentence == null || sentence.isEmpty()) {
                continue;
            }
            if (!sentence.contains("{}")) {
                text.add(sentence);
                continue;
            }
            String pos = (String) part[1];
            PickResult picked = pickWord(pos, buckets, usedIds);
            if (picked.row != null) {
                usedIds.add(toLong(picked.row.get("id")));
                used.add(picked.row);
            }
            text.add(sentence.replace("{}", picked.token));
        }

        List<String> paragraphs = toParagraphs(text, rng);
        Map<String, Object> article = new LinkedHashMap<>();
        article.put("date", dateStr);
        article.put("title", theme.get("title"));
        article.put("text", String.join("\n\n", paragraphs));
        article.put("words", toWordList(used));
        article.put("target_count", words.size());
        article.put("used_count", used.size());
        article.put("source", "template");
        return article;
    }

    /** 取词结果：填入词 + 单词行（可能为 null = 占位） */
    private static final class PickResult {
        final String token;
        final Map<String, Object> row;

        PickResult(String token, Map<String, Object> row) {
            this.token = token;
            this.row = row;
        }
    }

    /** 从对应词性桶取一个未用过的目标词；不足则退回「any」桶 */
    private static PickResult pickWord(String pos,
                                       Map<String, List<Map<String, Object>>> buckets,
                                       Set<Long> usedIds) {
        List<String> order = "any".equals(pos)
                ? List.of("any")
                : List.of(pos, "any");
        for (String key : order) {
            List<Map<String, Object>> bucket = buckets.getOrDefault(key, new ArrayList<>());
            for (int i = 0; i < bucket.size(); i++) {
                Map<String, Object> row = bucket.get(i);
                if (!usedIds.contains(toLong(row.get("id")))) {
                    String token = String.valueOf(row.get("word"));
                    bucket.remove(i);
                    return new PickResult(token, row);
                }
            }
        }
        return new PickResult(FILLER.getOrDefault(pos, FILLER.get("any")), null);
    }

    /** 把句子片段按 2~3 句一段打包成自然段落 */
    private static List<String> toParagraphs(List<String> parts, Random rng) {
        List<String> paras = new ArrayList<>();
        List<String> cur = new ArrayList<>();
        for (int i = 0; i < parts.size(); i++) {
            cur.add(parts.get(i));
            int size = 2 + rng.nextInt(2); // 2 或 3
            if (cur.size() >= size || i == parts.size() - 1) {
                paras.add(String.join("", cur).trim());
                cur.clear();
            }
        }
        return paras;
    }

    /** 把单词行列表压缩为文章词汇表（word/phonetic/meaning） */
    private static List<Map<String, Object>> toWordList(List<Map<String, Object>> rows) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> w : rows) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("word", String.valueOf(w.getOrDefault("word", "")));
            item.put("phonetic", String.valueOf(w.getOrDefault("phonetic", "")));
            item.put("meaning", String.valueOf(w.getOrDefault("meaning", "")));
            out.add(item);
        }
        return out;
    }

    // ------------------------------------------------------------------ //
    // AI 生成路径
    // ------------------------------------------------------------------ //

    /** 构造让大模型写复习文章的对话消息 */
    private static List<Map<String, String>> llmMessages(List<Map<String, Object>> words) {
        StringBuilder sb = new StringBuilder();
        for (Map<String, Object> w : words) {
            sb.append("- ").append(w.getOrDefault("word", ""))
              .append("  [").append(w.getOrDefault("phonetic", "")).append("]  ")
              .append(w.getOrDefault("meaning", "")).append("\n");
        }
        String system = "You are an English writing assistant for an IELTS vocabulary "
            + "review app. Write ONE short, coherent, natural English story "
            + "(150-220 words, 2-4 short paragraphs) that uses as many of the "
            + "given words as possible, each in a grammatically correct way. "
            + "Keep the language simple and clear for an intermediate learner. "
            + "Respond ONLY with JSON (no markdown fences), with exactly three "
            + "keys: \"title\" (a short title), \"text\" (the story, paragraphs "
            + "separated by a blank line), \"used_words\" (array of the exact "
            + "given words you used, in order of first appearance).";
        String user = "Here are the words to use (word | phonetic | meaning):\n"
            + sb + "\nNow write the story.";

        List<Map<String, String>> messages = new ArrayList<>();
        messages.add(Map.of("role", "system", "content", system));
        messages.add(Map.of("role", "user", "content", user));
        return messages;
    }

    /** 用大模型生成文章；成功返回文章 dict，失败返回 null（走模板兜底） */
    private Map<String, Object> generateWithLlm(String dateStr,
                                                List<Map<String, Object>> words) {
        String content;
        try {
            content = llm.complete(llmMessages(words));
        } catch (Exception e) {
            content = null;
        }
        if (content == null || content.isEmpty()) {
            return null;
        }
        Map<String, String> parsed = parseLlmArticle(content);
        if (parsed == null) {
            return null;
        }
        // 用到的词以「正文中出现」为准（即便模型漏了 used_words 也能补齐词表）
        List<Map<String, Object>> used = matchWordsInText(parsed.get("text"), words);
        Map<String, Object> article = new LinkedHashMap<>();
        article.put("date", dateStr);
        article.put("title", parsed.get("title"));
        article.put("text", parsed.get("text"));
        article.put("words", toWordList(used));
        article.put("target_count", words.size());
        article.put("used_count", used.size());
        article.put("source", "llm");
        return article;
    }

    /** 宽松解析模型返回的 JSON（容忍 markdown 围栏 / 多余文字） */
    private static Map<String, String> parseLlmArticle(String content) {
        JsonObject data = null;
        try {
            data = JsonParser.parseString(content).getAsJsonObject();
        } catch (Exception e) {
            Matcher m = Pattern.compile("\\{[\\s\\S]*\\}").matcher(content);
            if (m.find()) {
                try {
                    data = JsonParser.parseString(m.group()).getAsJsonObject();
                } catch (Exception ignored) {
                }
            }
        }
        if (data == null) {
            return null;
        }
        String title = optStr(data, "title");
        String text = optStr(data, "text");
        if (title.isEmpty() || text.isEmpty()) {
            return null;
        }
        Map<String, String> r = new LinkedHashMap<>();
        r.put("title", title);
        r.put("text", text);
        return r;
    }

    /** 找出正文中实际出现的目标词（支持常见词形变化） */
    private static List<Map<String, Object>> matchWordsInText(String text,
                                                              List<Map<String, Object>> words) {
        // 把正文按单词切分成 token（小写）
        Matcher m = Pattern.compile("[a-z]+").matcher(text.toLowerCase());
        Set<String> tokens = new LinkedHashSet<>();
        while (m.find()) {
            tokens.add(m.group());
        }
        // 常见英文词形变化后缀（用于判断 token 是否为原词的变形）
        Set<String> inflections = Set.of(
            "s", "es", "ed", "d", "ing", "ies", "ly", "er", "est", "ied",
            "en", "erly");

        List<Map<String, Object>> used = new ArrayList<>();
        for (Map<String, Object> w : words) {
            String word = String.valueOf(w.getOrDefault("word", "")).trim();
            String wl = word.toLowerCase();
            if (wl.isEmpty()) {
                continue;
            }
            if (tokens.contains(wl)) {
                used.add(w);
            } else if (wl.length() >= 3) {
                boolean hit = false;
                for (String t : tokens) {
                    if (t.startsWith(wl) && inflections.contains(t.substring(wl.length()))) {
                        hit = true;
                        break;
                    }
                }
                if (hit) {
                    used.add(w);
                }
            }
        }
        return used;
    }

    // ------------------------------------------------------------------ //
    // 对外便捷接口
    // ------------------------------------------------------------------ //

    /**
     * 读取某天文章；没有则生成并存档（换一篇时传新 seed 覆盖）。
     * 缓存刷新规则：若当天存档是「模板版」而现在已启用 AI，
     * 则自动用 AI 重生成并覆盖；已是 AI 版或未启用 AI 时直接返回存档。
     */
    public Map<String, Object> getOrGenerate(String dateStr, String seed,
                                             int days, int limit) {
        if (dateStr == null) {
            dateStr = LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE);
        }
        Map<String, Object> art = load(dateStr);
        if (art == null) {
            art = generate(dateStr, seed, days, limit);
            save(dateStr, art);
            return art;
        }
        // 已有存档且之前是模板版、现在启用了 AI -> 用 AI 重生成升级
        boolean llmOn = llm != null && llm.enabled();
        if (llmOn && !"llm".equals(String.valueOf(art.get("source")))) {
            Map<String, Object> fresh = generate(dateStr, seed, days, limit);
            // 只有真的生成了 AI 版才覆盖存档（AI 失败回落模板时不覆盖）
            if ("llm".equals(String.valueOf(fresh.get("source")))) {
                save(dateStr, fresh);
                return fresh;
            }
        }
        return art;
    }

    /** 返回某天的前一天（"YYYY-MM-DD"） */
    public static String dateBefore(String dateStr) {
        return LocalDate.parse(dateStr).minusDays(1).toString();
    }

    /** 返回某天的后一天（"YYYY-MM-DD"） */
    public static String dateAfter(String dateStr) {
        return LocalDate.parse(dateStr).plusDays(1).toString();
    }

    // ------------------------------------------------------------------ //
    // 工具
    // ------------------------------------------------------------------ //

    private static long toLong(Object o) {
        if (o instanceof Number) {
            return ((Number) o).longValue();
        }
        try {
            return Long.parseLong(String.valueOf(o));
        } catch (Exception e) {
            return -1L;
        }
    }

    private static String optStr(JsonObject obj, String key) {
        JsonElement el = obj.get(key);
        if (el == null || el.isJsonNull()) {
            return "";
        }
        return el.getAsString().trim();
    }
}
