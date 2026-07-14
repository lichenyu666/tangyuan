# RAG Demo 示例知识库

这是一个开箱即用的 RAG（检索增强生成）示例。目录里的 Markdown 就是「知识库」，
`tangyuan rag` 会先在这些文件里检索相关内容，再让 LLM 依据它作答并给出引用。

## 试一下

```bash
# 在仓库根目录，配好 .env（含 TANGYUAN_API_KEY）后：
tangyuan rag "汤圆的记忆系统是怎么分层的？" -w examples/rag_demo
tangyuan rag "什么是 RAG？它分哪几步？" -w examples/rag_demo
tangyuan rag "在线 Demo 关掉了哪些危险工具？" -w examples/rag_demo
```

输出会包含：LLM 的回答（句中用 `[1][2]` 标注引用）+ 底部列出引用来源（文件:行号）。

## 换成你自己的资料

把 `-w` 指向任意包含 `.md` / `.txt` 等文本的目录即可，例如你的学习笔记、
产品文档、论文摘录。首次查询会自动建索引（存到该目录的 `.tangyuan/semantic.db`）。
