package com.summarizer.pojo;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.util.List;

@Data
@AllArgsConstructor
public class JFile {
  private Integer id;
  private String name;
  private String signature;
  private List<JMethod> methods;
  private String path;
}
