# TeacherHelper — business flow: Topic Studio

```mermaid
flowchart TD
    start([Teacher opens Topic Studio]) --> input[Enter topic, level and learning intent]
    input --> sources{Use uploaded sources?}
    sources -- Yes --> retrieve[Retrieve relevant library material]
    sources -- No --> outline[Build topic outline]
    retrieve --> outline
    outline --> choose[Choose activity or material type]
    choose --> create[Generate selected teaching asset]
    create --> review[Teacher reviews and refines output]
    review --> save[Save approved asset to library]
    save --> end([Topic materials ready])
```
