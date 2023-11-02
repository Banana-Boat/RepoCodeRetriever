package com.summarizer.pojo;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class JRepo {
    private JDirectory mainDirectory;
    private Integer nodeCount;
}
