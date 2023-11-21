package com.summarizer.pojo;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.util.List;

@Data
@AllArgsConstructor
public class JDirectory {
  private Integer id;
  private String name;
  private String path;
  private List<JFile> files;
  private List<JDirectory> subdirectories;
}
