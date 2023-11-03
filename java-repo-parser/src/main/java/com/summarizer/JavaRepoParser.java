package com.summarizer;

import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.*;
import com.github.javaparser.ast.stmt.BlockStmt;
import com.github.javaparser.ast.stmt.Statement;
import com.github.javaparser.ast.stmt.SwitchEntry;
import com.github.javaparser.ast.visitor.VoidVisitorAdapter;
import com.summarizer.pojo.*;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class JavaRepoParser {
    private static final String BLOCK_PLACEHOLDER = "<BLOCK>";
    private Tokenizer tokenizer;
    private ParserConfiguration.LanguageLevel languageLevel;
    private int nodeCount = 0; // number of nodes
    private int dirCount = 0; // number of directories
    private int fileCount = 0; // number of files
    private int errorFileCount = 0; // number of parsing error file
    private int cutCount = 0; // number of cut code snippets
    private int totalCutCharCount = 0; // use to calculate average number of cut tokens
    public List<String> logs = new ArrayList<>(); // parse logs

    public JavaRepoParser(Tokenizer tokenizer, ParserConfiguration.LanguageLevel languageLevel) {
        this.tokenizer = tokenizer;
        this.languageLevel = languageLevel;
    }

    public JRepo extractRepo(File dir) throws Exception {
        if (!dir.isDirectory())
            throw new IllegalArgumentException("param is not a directory");

        JDirectory jDirectory = extractDirectory(dir, dir.getName());

        logs.add(0, "Number of directories containing java file：" + dirCount +
                        "\nNumber of java files：" + fileCount +
                        "\nNumber of parsing error files：" + errorFileCount +
                        "\nNumber of cut code snippets：" + cutCount +
                        "\nNumber of node：" + nodeCount +
                        "\nAverage number of cut tokens：" + (cutCount != 0 ? (double) totalCutCharCount / cutCount : "/"));

        return new JRepo(
                jDirectory,
                nodeCount
        );
    }

    public JDirectory extractDirectory(File dir, String pkgName) throws Exception {
        if (!dir.isDirectory())
            throw new IllegalArgumentException("param is not a directory");

        ArrayList<JDirectory> subJDirectories = new ArrayList<>();
        ArrayList<JFile> jFiles = new ArrayList<>();

        File[] subFiles = Objects.requireNonNull(dir.listFiles());
//        // process current directory with only one subdirectory, concat directory name, only generate one node.
//        if (subFiles.length == 1 && subFiles[0].isDirectory()) {
//            return extractDirectory(subFiles[0], pkgName + "/" + subFiles[0].getName());
//        }

        for (File file : subFiles) {
            if (file.isDirectory()) {
                JDirectory jDirectory = extractDirectory(file, file.getName());
                if (jDirectory != null)
                    subJDirectories.add(jDirectory);
            } else {
                if (file.getName().endsWith(".java")) {
                    jFiles.add(extractFile(file));
                }
            }
        }

        // if current directory has no subdirectory and no java file, return null
        if(jFiles.size() == 0 && subJDirectories.size() == 0)
            return null;

        nodeCount++;
        dirCount++;
        return new JDirectory(
                pkgName,
                dir.getPath(),
                jFiles,
                subJDirectories
        );
    }

    public JFile extractFile(File file) {
        ArrayList<JClass> jClasses = new ArrayList<>();

        try {
            StaticJavaParser.setConfiguration(
                    new ParserConfiguration().setLanguageLevel(languageLevel)
            );
            CompilationUnit cu = StaticJavaParser.parse(file);

            // get current file's all classes / interfaces / enums
            // if there are nested inner classes, flatten them directly
            cu.accept(new VoidVisitorAdapter<Void>() {
                @Override
                public void visit(CompilationUnit cu, Void arg) {
                    super.visit(cu, arg);

                    for (ClassOrInterfaceDeclaration coi : cu.findAll(ClassOrInterfaceDeclaration.class)) {
                        // concat signature
                        String signature = (coi.isAbstract() ? "abstract " : "") +
                                (coi.isInterface() ? "interface " : "class ") + coi.getNameAsString() +
                                ((coi.getExtendedTypes().size() == 0) ? "" :
                                        " extends " + coi.getExtendedTypes().toString()
                                                .replace("[", "").replace("]", "")) +
                                ((coi.getImplementedTypes().size() == 0) ? "" :
                                        " implements " + coi.getImplementedTypes().toString()
                                                .replace("[", "").replace("]", ""));

                        nodeCount++;
                        jClasses.add(new JClass(
                                coi.getNameAsString(),
                                signature,
                                extractMethods(coi, file.getPath())
                        ));
                    }

                    for (EnumDeclaration e : cu.findAll(EnumDeclaration.class)) {
                        // concat signature
                        String signature = "enum " + e.getNameAsString() +
                                ((e.getImplementedTypes().size() == 0) ? "" :
                                        " implements " + e.getImplementedTypes().toString()
                                                .replace("[", "").replace("]", ""));

                        nodeCount++;
                        jClasses.add(new JClass(
                                e.getNameAsString(),
                                signature,
                                extractMethods(e, file.getPath())
                        ));
                    }
                }
            }, null);
        } catch (Exception e) {
            logs.add(file.getPath() + " can't be parsed for:\n" + e.getMessage());
            errorFileCount++;
        }

        fileCount++;
        return new JFile(
                file.getName(),
                jClasses,
                file.getPath()
        );
    }

    public List<JMethod> extractMethods(TypeDeclaration td, String filePath) {
        ArrayList<JMethod> jMethods = new ArrayList<>();

        List<FieldDeclaration> fields = td.getFields();

        for (Object obj : td.getMethods()) {
            MethodDeclaration md = (MethodDeclaration) obj;

            // ignore empty func / constructor / toString / hashCode / equals
            if (md.getBody().isEmpty() ||
                    md.isConstructorDeclaration() ||
                    md.getNameAsString().equals("toString") ||
                    md.getNameAsString().equals("hashCode") ||
                    md.getNameAsString().equals("equals")) {
                continue;
            }

            // ignore getter / setter
            List<String> getterAndSetterMethods = new ArrayList<>();
            fields.forEach(field -> {
                String fieldName = field.getVariable(0).getNameAsString();
                fieldName = fieldName.substring(0, 1).toUpperCase() + fieldName.substring(1);
                getterAndSetterMethods.add("get" + fieldName);
                getterAndSetterMethods.add("set" + fieldName);
            });
            if (getterAndSetterMethods.contains(md.getNameAsString())) {
                continue;
            }

            String signature = md.getType() + " " + md.getName() +
                    md.getParameters().toString().replace("[", "(").replace("]", ")");

            JCodeSnippet jCodeSnippet;
            BlockStmt body = md.getBody().get();
            if (!tokenizer.isLegalSource(signature + body)) {
                jCodeSnippet = splitCodeSnippet(body, formatCodeSnippet(body.toString()), filePath);
            } else {
                nodeCount++;
                jCodeSnippet = new JCodeSnippet(formatCodeSnippet(body.toString()), new ArrayList<>());
            }

            jMethods.add(new JMethod(
                    md.getNameAsString(),
                    signature,
                    jCodeSnippet.getContent(),
                    jCodeSnippet.getCodeSnippets()
            ));
        }

        return jMethods;
    }

    /**
     * 将一个代码片段分割为多个长度不超过 MAX_LLM_LENGTH 的代码片段
     * TODO： 无法处理多个较短的语句构成的代码片段
     *
     * @param body    待处理的语句节点
     * @param content 该语句节点（可以为其父节点）的字符串内容（未替换占位符）
     */
    public JCodeSnippet splitCodeSnippet(Statement body, String content, String filePath) {
        ArrayList<JCodeSnippet> jCodeSnippets = new ArrayList<>();

        for (Statement stmt : body.findAll(Statement.class, s -> s.getParentNode().get() == body)) {
            String codeSnippet = formatCodeSnippet(stmt.toString());

            if (!tokenizer.isLegalCodeSnippet(codeSnippet)) {
                switch (stmt.getClass().getSimpleName()) {
                    case "IfStmt":
                        Statement thenStmt = stmt.asIfStmt().getThenStmt();
                        String ifBlockContent = "if (" + stmt.asIfStmt().getCondition() + ") " + formatCodeSnippet(thenStmt.toString());

                        if (stmt.asIfStmt().getElseStmt().isPresent()) { // if there has else-if / else, process recursively
                            Statement elseStmt = stmt.asIfStmt().getElseStmt().get();
                            String elseBlockContent = "else " + formatCodeSnippet(elseStmt.toString());

                            // 判断若then中内容替换后，if-else整体是否超过上限（因为存在递归关系）
                            if (!tokenizer.isLegalCodeSnippet(replaceOnce(content, ifBlockContent, BLOCK_PLACEHOLDER))) {
                                // 若仍然超过则分别对then和else进行分割，并替换为两个占位符
                                jCodeSnippets.add(splitCodeSnippet(thenStmt, ifBlockContent, filePath));
                                jCodeSnippets.add(splitCodeSnippet(elseStmt, elseBlockContent, filePath));
                                content = replaceOnce(content, ifBlockContent, BLOCK_PLACEHOLDER);
                                content = replaceOnce(content, elseBlockContent, BLOCK_PLACEHOLDER);
                            } else {
                                // 若未超过则只对then进行分割，并替换为一个占位符
                                String tempContent = ifBlockContent + " " + elseBlockContent;
                                jCodeSnippets.add(splitCodeSnippet(thenStmt, tempContent, filePath));
                                content = replaceOnce(content, tempContent, BLOCK_PLACEHOLDER);
                            }
                        } else { // if there has no else-if / else
                            jCodeSnippets.add(splitCodeSnippet(thenStmt, ifBlockContent, filePath));
                            content = replaceOnce(content, ifBlockContent, BLOCK_PLACEHOLDER);
                        }
                        break;
                    case "SwitchStmt":
                        for (SwitchEntry entry : stmt.asSwitchStmt().getEntries()) {
                            for (Statement statement : entry.getStatements()) {
                                String statementContent = formatCodeSnippet(statement.toString());
                                if (!tokenizer.isLegalCodeSnippet(statementContent)) {
                                    jCodeSnippets.add(splitCodeSnippet(statement, statementContent, filePath));
                                    content = replaceOnce(content, statementContent, BLOCK_PLACEHOLDER);
                                }
                            }
                        }
                        break;
                    case "TryStmt":
                        jCodeSnippets.add(splitCodeSnippet(stmt.asTryStmt().getTryBlock(), codeSnippet, filePath));
                        content = replaceOnce(content, codeSnippet, BLOCK_PLACEHOLDER);
                        // don't split catch and finally, cut directly if exceed
                        break;
                    case "ForStmt":
                        jCodeSnippets.add(splitCodeSnippet(stmt.asForStmt().getBody(), codeSnippet, filePath));
                        content = replaceOnce(content, codeSnippet, BLOCK_PLACEHOLDER);
                        break;
                    case "WhileStmt":
                        jCodeSnippets.add(splitCodeSnippet(stmt.asWhileStmt().getBody(), codeSnippet, filePath));
                        content = replaceOnce(content, codeSnippet, BLOCK_PLACEHOLDER);
                        break;
                    case "DoStmt":
                        jCodeSnippets.add(splitCodeSnippet(stmt.asDoStmt().getBody(), codeSnippet, filePath));
                        content = replaceOnce(content, codeSnippet, BLOCK_PLACEHOLDER);
                        break;
                    case "ForEachStmt":
                        jCodeSnippets.add(splitCodeSnippet(stmt.asForEachStmt().getBody(), codeSnippet, filePath));
                        content = replaceOnce(content, codeSnippet, BLOCK_PLACEHOLDER);
                        break;
                    case "SynchronizedStmt":
                        jCodeSnippets.add(splitCodeSnippet(stmt.asSynchronizedStmt().getBody(), codeSnippet, filePath));
                        content = replaceOnce(content, codeSnippet, BLOCK_PLACEHOLDER);
                        break;
                    default:
                        logs.add(filePath + "\n" + stmt.getRange().get() + "\n" +
                                "Unhandled long statement type: " + stmt.getClass().getSimpleName());
                        jCodeSnippets.add(splitCodeSnippet(stmt, codeSnippet, filePath));
                        content = replaceOnce(content, codeSnippet, BLOCK_PLACEHOLDER);
                }
            }
        }

        // if still exceed after splitting, cut directly
        if (!tokenizer.isLegalSource(content)) {
            totalCutCharCount += tokenizer.getTokenNum(content) - tokenizer.getMaxSourceLength();
            cutCount++;

            String cutContent = tokenizer.cutToLegalSource(content);

            logs.add(filePath + "\n" + body.getRange().get() + "\n" +
                    "cut off from: \n" + content + "\n" +
                    "to: \n" + cutContent);

            content = cutContent;
        }

        nodeCount++;
        return new JCodeSnippet(content, jCodeSnippets);
    }

    // 替换第一个匹配的字符串。String自带的方法第一个参数为正则表达式，而待替换的代码片段存在存在正则中的特殊字符，故自行实现
    public String replaceOnce(String str, String target, String replacement) {
        int idx = str.indexOf(target);
        if (idx == -1) {
            return str;
        } else {
            return str.substring(0, idx) + replacement + str.substring(idx + target.length());
        }
    }

    public String formatCodeSnippet(String codeSnippet) {
        return codeSnippet.replaceAll("\n", " ")
                .replaceAll(" +", " ");
    }
}