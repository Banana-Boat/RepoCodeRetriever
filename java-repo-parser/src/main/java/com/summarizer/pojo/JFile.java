package com.summarizer.pojo;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.util.List;

@Data
@AllArgsConstructor
public class JFile {
  private String name;
  private List<JClass> classes;
  private String path;
}
