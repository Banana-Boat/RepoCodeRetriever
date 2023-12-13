package com.summarizer;

import com.alibaba.fastjson.JSON;
import com.github.javaparser.ParserConfiguration;
import com.summarizer.pojo.JRepo;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import picocli.CommandLine;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

import java.io.File;
import java.io.FileWriter;

@Command(name = "JavaRepoParser", mixinStandardHelpOptions = true, version = "JavaRepoParser 1.0")
public class Main implements Runnable {
    @Option(names = {"-r", "--repo-path"}, description = "Path to the directory of repository", required = true)
    private String repoPath = "";
    @Option(names = {"-o", "--output-path"}, description = "Path to the output file")
    private String outputPath = "./parse_output.json";
    @Option(names = {"-v", "--lang-version"}, description = "Version of the Java language", defaultValue = "17")
    private String langVersion = "17";

    public static void main(String[] args) {
        int exitCode = new CommandLine(new Main()).execute(args);
        System.exit(exitCode);
    }

    @Override
    public void run() {
        Logger logger = LoggerFactory.getLogger(Main.class);

        File dir = new File(repoPath);
        if (!dir.isDirectory()) {
            logger.error("JavaRepoParser: " + repoPath + " is not a directory");
            System.exit(1);
        }

        JavaRepoParser parser = new JavaRepoParser(getLanguageLevel());

        // parse and write result
        try {
            JRepo jRepo = parser.extractRepo(dir);

            try (FileWriter fw = new FileWriter(outputPath)) {
                String json = JSON.toJSONString(jRepo);
                fw.write(json);
            } catch (Exception e) {
                e.printStackTrace();
                System.exit(1);
            }
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(1);
        }
    }

    public ParserConfiguration.LanguageLevel getLanguageLevel() {
        return switch (langVersion) {
            case "1.0" -> ParserConfiguration.LanguageLevel.JAVA_1_0;
            case "1.1" -> ParserConfiguration.LanguageLevel.JAVA_1_1;
            case "1.2" -> ParserConfiguration.LanguageLevel.JAVA_1_2;
            case "1.3" -> ParserConfiguration.LanguageLevel.JAVA_1_3;
            case "1.4" -> ParserConfiguration.LanguageLevel.JAVA_1_4;
            case "1.5" -> ParserConfiguration.LanguageLevel.JAVA_5;
            case "1.6" -> ParserConfiguration.LanguageLevel.JAVA_6;
            case "1.7" -> ParserConfiguration.LanguageLevel.JAVA_7;
            case "1.8" -> ParserConfiguration.LanguageLevel.JAVA_8;
            case "9" -> ParserConfiguration.LanguageLevel.JAVA_9;
            case "10" -> ParserConfiguration.LanguageLevel.JAVA_10;
            case "11" -> ParserConfiguration.LanguageLevel.JAVA_11;
            case "12" -> ParserConfiguration.LanguageLevel.JAVA_12;
            case "13" -> ParserConfiguration.LanguageLevel.JAVA_13;
            case "14" -> ParserConfiguration.LanguageLevel.JAVA_14;
            case "15" -> ParserConfiguration.LanguageLevel.JAVA_15;
            case "16" -> ParserConfiguration.LanguageLevel.JAVA_16;
            case "17" -> ParserConfiguration.LanguageLevel.JAVA_17;
            default -> ParserConfiguration.LanguageLevel.JAVA_17;
        };
    }

}