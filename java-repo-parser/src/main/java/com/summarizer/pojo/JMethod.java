package com.summarizer.pojo;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class JMethod {
    private Integer id;
    private  String name;
    private String signature;
    private String body;
}
