# Skills（工作区覆盖用）

内置剧本在包内：`tangyuan/skills/catalog/`。

若要在本仓库覆盖/新增 Skill，在此目录下建：

```text
skills/<id>/SKILL.md
```

汤圆加载顺序：
1. 当前 workspace 的 `skills/`（本目录，若有内容）
2. 否则用内置 `tangyuan/skills/catalog/`
