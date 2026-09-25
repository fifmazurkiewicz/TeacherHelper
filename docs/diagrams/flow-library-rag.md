# TeacherHelper — business flow: library upload and semantic search

```mermaid
flowchart TD
    start([Teacher uploads a source file]) --> store[Store source file and ownership metadata]
    store --> extract[Extract text and split into chunks]
    extract --> embed[Create embeddings for searchable chunks]
    embed --> index[Write chunks to vector index]
    index --> ready([Source becomes searchable])
    search([Teacher asks a library question]) --> query[Embed query and search allowed sources]
    query --> retrieve[Retrieve relevant chunks with citations]
    retrieve --> answer[Use sources in answer or generated material]
    answer --> end([Teacher reviews source-grounded result])
```
