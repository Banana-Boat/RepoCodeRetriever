package com.summarizer;

import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.*;
import com.github.javaparser.ast.visitor.VoidVisitorAdapter;
import com.summarizer.pojo.*;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class JavaRepoParser {
    private ParserConfiguration.LanguageLevel languageLevel;
    private int nodeCount = 0; // number of nodes
    private int maxSubDirCount = 0; // max number of subdirectories in a directory
    private int maxFileCount = 0; // max number of files in a directory
    private int maxSubDirAndFileCount = 0; // max number of subdirectories and files in a directory
    private int totalDirCount = 0; // total number of directories
    private int totalFileCount = 0; // total number of files
    private int errorFileCount = 0; // number of parsing error file
    public List<String> logs = new ArrayList<>(); // parse logs

    public JavaRepoParser(ParserConfiguration.LanguageLevel languageLevel) {
        this.languageLevel = languageLevel;
    }

    public JRepo extractRepo(File dir) throws Exception {
        if (!dir.isDirectory())
            throw new IllegalArgumentException("param is not a directory");

        JDirectory jDirectory = extractDirectory(dir, dir.getName());

        logs.add(0, "Number of parsing error files：" + errorFileCount);

        return new JRepo(
                jDirectory,
                nodeCount,
                maxSubDirCount,
                maxFileCount,
                maxSubDirAndFileCount,
                totalDirCount,
                totalFileCount
        );
    }

    public JDirectory extractDirectory(File dir, String dirName) throws Exception {
        if (!dir.isDirectory())
            throw new IllegalArgumentException("param is not a directory");

        ArrayList<JDirectory> subJDirectories = new ArrayList<>();
        ArrayList<JFile> jFiles = new ArrayList<>();

        File[] subFiles = Objects.requireNonNull(dir.listFiles());

        for (File file : subFiles) {
            if (file.isDirectory()) {
                // if directory name contains test, skip it
                if (file.getName().toLowerCase().contains("test"))
                    continue;

                JDirectory jDirectory = extractDirectory(file, file.getName());
                if (jDirectory != null)
                    subJDirectories.add(jDirectory);
            } else {
                if (file.getName().endsWith(".java")) {
                    JFile jFile = extractFile(file);
                    if (jFile != null)
                        jFiles.add(jFile);
                }
            }
        }

        // if current directory has no subdirectory and no java file, return null
        if(jFiles.size() == 0 && subJDirectories.size() == 0)
            return null;

        nodeCount++;
        totalDirCount++;
        totalFileCount += jFiles.size();
        maxSubDirCount = Math.max(maxSubDirCount, subJDirectories.size());
        maxFileCount = Math.max(maxFileCount, jFiles.size());
        maxSubDirAndFileCount = Math.max(maxSubDirAndFileCount, subJDirectories.size() + jFiles.size());
        return new JDirectory(
                nodeCount,
                dirName,
                jFiles,
                subJDirectories
        );
    }

    public JFile extractFile(File file) {
        class JClassContainer {
            boolean isFoundCls = false;
            String signature;
            List<JMethod> methods;
            void setInfo(String signature, List<JMethod> methods) {
                this.isFoundCls = true;
                this.signature = signature;
                this.methods = methods;
            }
        }

        JClassContainer jClassContainer = new JClassContainer();

        try {
            StaticJavaParser.setConfiguration(
                    new ParserConfiguration().setLanguageLevel(languageLevel)
            );
            CompilationUnit cu = StaticJavaParser.parse(file);

            cu.accept(new VoidVisitorAdapter<Void>() {
                @Override
                public void visit(CompilationUnit cu, Void arg) {
                    super.visit(cu, arg);

                    // inner class and non-public class will be found at first
                    for (ClassOrInterfaceDeclaration coi : cu.findAll(ClassOrInterfaceDeclaration.class)) {
                        if (coi.isInterface()) continue;

                        // only save the class with the same name as the file name
                        if (!file.getName().split("\\.")[0].equals(coi.getNameAsString()))
                            continue;

                        // concat signature
                        String signature = (coi.isAbstract() ? "abstract " : "") +
                                "class " + coi.getNameAsString() +
                                ((coi.getExtendedTypes().size() == 0) ? "" :
                                        " extends " + coi.getExtendedTypes().toString()
                                                .replace("[", "").replace("]", "")) +
                                ((coi.getImplementedTypes().size() == 0) ? "" :
                                        " implements " + coi.getImplementedTypes().toString()
                                                .replace("[", "").replace("]", ""));


                        jClassContainer.setInfo(
                                signature,
                                extractMethods(coi)
                        );
                    }
                }
            }, null);
        } catch (Exception e) {
            System.out.println(file.getPath() + " can't be parsed for:\n" + e.getMessage());
            throw new RuntimeException(e);
        }

        if(!jClassContainer.isFoundCls || jClassContainer.methods.size() == 0)
            return null;

        nodeCount++;
        return new JFile(
                nodeCount,
                file.getName(),
                jClassContainer.signature,
                jClassContainer.methods
        );
    }

    public List<JMethod> extractMethods(TypeDeclaration td) {
        ArrayList<JMethod> jMethods = new ArrayList<>();

        List<FieldDeclaration> fields = td.getFields();

        for (Object obj : td.getMethods()) {
            MethodDeclaration md = (MethodDeclaration) obj;

            // ignore toString / hashCode / equals
            if (md.getNameAsString().equals("toString") ||
                    md.getNameAsString().equals("hashCode") ||
                    md.getNameAsString().equals("equals")) {
                continue;
            }

            // ignore getter / setter of fields
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


            String bodyContent = md.getBody().isEmpty() ? "" : formatCodeSnippet(md.getBody().get().toString());

            nodeCount++;
            jMethods.add(new JMethod(
                    nodeCount,
                    md.getNameAsString(),
                    signature,
                    bodyContent
            ));
        }

        return jMethods;
    }

    public String formatCodeSnippet(String codeSnippet) {
        return codeSnippet.replaceAll("\n", " ")
                .replaceAll(" +", " ");
    }
}