package com.summarizer.pojo;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class JRepo {
    private JDirectory mainDirectory;
    private Integer nodeCount;
    private Integer maxSubDirCount;
    private Integer maxFileCount;
    private Integer maxSubDirAndFileCount;
    private Integer totalDirCount;
    private Integer totalFileCount;
}
