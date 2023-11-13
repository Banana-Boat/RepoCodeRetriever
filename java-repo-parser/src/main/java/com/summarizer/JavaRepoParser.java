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
    private int dirCount = 0; // number of directories
    private int fileCount = 0; // number of files
    private int errorFileCount = 0; // number of parsing error file
    public List<String> logs = new ArrayList<>(); // parse logs

    public JavaRepoParser(ParserConfiguration.LanguageLevel languageLevel) {
        this.languageLevel = languageLevel;
    }

    public JRepo extractRepo(File dir) throws Exception {
        if (!dir.isDirectory())
            throw new IllegalArgumentException("param is not a directory");

        JDirectory jDirectory = extractDirectory(dir, dir.getName());

        logs.add(0, "Number of node：" + nodeCount +
                        "\nNumber of directories containing java file：" + dirCount +
                        "\nNumber of java files：" + fileCount +
                        "\nNumber of parsing error files：" + errorFileCount);

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
                                extractMethods(coi)
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
                                extractMethods(e)
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

    public List<JMethod> extractMethods(TypeDeclaration td) {
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

            String bodyContent = formatCodeSnippet(md.getBody().get().toString());

            nodeCount++;
            jMethods.add(new JMethod(
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